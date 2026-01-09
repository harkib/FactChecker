#!/bin/bash
# Debug script for Lambda function
# Run from infra directory

set -e

FUNCTION_NAME="factchecker-url-to-video"
REGION=${AWS_REGION:-"us-east-1"}

echo "=== Lambda Function Debug ==="
echo "Function: $FUNCTION_NAME"
echo "Region: $REGION"
echo ""

echo "1. Function Status:"
aws lambda get-function-configuration \
    --function-name $FUNCTION_NAME \
    --region $REGION \
    --query '{State:State,LastUpdateStatus:LastUpdateStatus,LastUpdateStatusReason:LastUpdateStatusReason,Timeout:Timeout,Memory:MemorySize}' \
    --output table

echo ""
echo "2. Recent Invocations (last 5 minutes):"
END_TIME=$(date -u +%s)
START_TIME=$((END_TIME - 300))
aws logs filter-log-events \
    --log-group-name "/aws/lambda/$FUNCTION_NAME" \
    --start-time ${START_TIME}000 \
    --end-time ${END_TIME}000 \
    --region $REGION \
    --query 'events[*].message' \
    --output text | tail -20 || echo "  (No recent logs found)"

echo ""
echo "3. Recent Errors:"
aws logs filter-log-events \
    --log-group-name "/aws/lambda/$FUNCTION_NAME" \
    --start-time ${START_TIME}000 \
    --end-time ${END_TIME}000 \
    --filter-pattern "ERROR" \
    --region $REGION \
    --query 'events[*].message' \
    --output text | tail -10 || echo "  (No errors found)"

echo ""
echo "4. Event Source Mapping Status:"
aws lambda list-event-source-mappings \
    --function-name $FUNCTION_NAME \
    --region $REGION \
    --query 'EventSourceMappings[*].{UUID:UUID,State:State,LastProcessingResult:LastProcessingResult,StateTransitionReason:StateTransitionReason}' \
    --output table || echo "  (No event source mappings found)"

echo ""
echo "5. Queue Status:"
QUEUE_URL=$(aws sqs get-queue-url --queue-name factchecker-url-to-video --region $REGION --query 'QueueUrl' --output text 2>/dev/null)
if [ -n "$QUEUE_URL" ]; then
    aws sqs get-queue-attributes \
        --queue-url "$QUEUE_URL" \
        --attribute-names All \
        --region $REGION \
        --query 'Attributes.{ApproximateNumberOfMessages:ApproximateNumberOfMessages,ApproximateNumberOfMessagesNotVisible:ApproximateNumberOfMessagesNotVisible,ApproximateNumberOfMessagesDelayed:ApproximateNumberOfMessagesDelayed}' \
        --output table
else
    echo "  (Queue not found)"
fi

echo ""
echo "=== Quick Debug Commands ==="
echo ""
echo "View live logs:"
echo "  aws logs tail /aws/lambda/$FUNCTION_NAME --follow --region $REGION"
echo ""
echo "View all recent logs:"
echo "  aws logs filter-log-events --log-group-name /aws/lambda/$FUNCTION_NAME --region $REGION --start-time \$(date -u -d '5 minutes ago' +%s)000 --query 'events[*].message' --output text"
echo ""
echo "Test Lambda manually:"
echo "  aws lambda invoke --function-name $FUNCTION_NAME --payload '{\"Records\":[{\"messageId\":\"test\",\"body\":\"{\\\"job_id\\\":\\\"test-123\\\",\\\"video_url\\\":\\\"https://example.com\\\"}\"}]}' response.json --region $REGION && cat response.json"
echo ""
echo "Check Lambda in Console:"
echo "  https://console.aws.amazon.com/lambda/home?region=$REGION#/functions/$FUNCTION_NAME"

