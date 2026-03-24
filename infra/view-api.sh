#!/bin/bash
# Script to view deployed API components

set -e

echo "=== FactChecker API Components ==="
echo ""

# Get the stack name (assuming default naming)
STACK_NAME="ApiStack"
REGION="${AWS_REGION:-us-east-1}"

echo "1. API Endpoint (API Gateway):"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
  --output text 2>/dev/null || echo "  (Output not found - may need to redeploy with outputs)"

echo ""
echo "2. Health Check Endpoint:"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiHealthCheck`].OutputValue' \
  --output text 2>/dev/null || echo "  (Output not found - may need to redeploy with outputs)"

echo ""
echo "3. API Key:"
API_KEY_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiKeyId`].OutputValue' \
  --output text 2>/dev/null)

if [ -n "$API_KEY_ID" ] && [ "$API_KEY_ID" != "None" ]; then
  echo "  API Key ID: $API_KEY_ID"
  API_KEY_VALUE=$(aws apigateway get-api-key \
    --api-key "$API_KEY_ID" \
    --include-value \
    --region "$REGION" \
    --query 'value' \
    --output text 2>/dev/null)

  if [ -n "$API_KEY_VALUE" ]; then
    echo "  API Key Value: $API_KEY_VALUE"
    echo ""
    echo "  Usage: Add this header to your API requests:"
    echo "    x-api-key: $API_KEY_VALUE"
  else
    echo "  (Could not retrieve API key value - check AWS permissions)"
  fi
else
  echo "  (API Key ID not found in stack outputs)"
fi

echo ""
echo "4. EC2 Instance Details:"
EC2_IP=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`Ec2PublicIp`].OutputValue' \
  --output text 2>/dev/null)

INSTANCE_ID=$(aws cloudformation describe-stack-resources \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'StackResources[?ResourceType==`AWS::EC2::Instance`].PhysicalResourceId' \
  --output text 2>/dev/null | head -1)

if [ -n "$INSTANCE_ID" ]; then
  echo "  Instance ID: $INSTANCE_ID"
  echo "  Elastic IP: $EC2_IP"

  aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION" \
    --query 'Reservations[0].Instances[0].{State:State.Name,Type:InstanceType,LaunchTime:LaunchTime}' \
    --output table 2>/dev/null || echo "  (Could not fetch instance status)"
else
  echo "  (EC2 instance not found)"
fi

echo ""
echo "5. Test API Health Endpoint:"
if [ -n "$EC2_IP" ]; then
  echo "  Testing: http://$EC2_IP:8000/health"
  curl -s -o /dev/null -w "  Status: %{http_code}\n" "http://$EC2_IP:8000/health" || echo "  (Could not reach endpoint - instance may still be starting)"
else
  echo "  (EC2 IP not available)"
fi

echo ""
echo "=== Quick Access Commands ==="
echo ""
echo "Get API endpoint:"
echo "  aws cloudformation describe-stacks --stack-name ApiStack --query 'Stacks[0].Outputs[?OutputKey==\`ApiEndpoint\`].OutputValue' --output text"
echo ""
echo "Get API key:"
echo "  API_KEY_ID=\$(aws cloudformation describe-stacks --stack-name ApiStack --query 'Stacks[0].Outputs[?OutputKey==\`ApiKeyId\`].OutputValue' --output text)"
echo "  aws apigateway get-api-key --api-key \$API_KEY_ID --include-value --query 'value' --output text"
echo ""
echo "Test health endpoint:"
if [ -n "$EC2_IP" ]; then
  echo "  curl http://$EC2_IP:8000/health"
else
  echo "  curl http://<EC2_ELASTIC_IP>:8000/health"
fi
echo ""
echo "SSH via SSM Session Manager:"
if [ -n "$INSTANCE_ID" ]; then
  echo "  aws ssm start-session --target $INSTANCE_ID"
else
  echo "  aws ssm start-session --target <INSTANCE_ID>"
fi
echo ""
echo "View in AWS Console:"
echo "  EC2: https://console.aws.amazon.com/ec2/v2/home#Instances:"
echo "  API Gateway: https://console.aws.amazon.com/apigateway"
echo "  CloudFormation: https://console.aws.amazon.com/cloudformation/home#/stacks"
