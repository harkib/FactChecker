#!/bin/bash
# View Lambda functions for FactChecker
# Run from infra directory

set -e

AWS_REGION=${AWS_REGION:-"us-east-1"}

echo "Lambda Functions in region: $AWS_REGION"
echo "========================================"
echo ""

# List all Lambda functions with factchecker prefix
aws lambda list-functions \
    --region $AWS_REGION \
    --query 'Functions[?starts_with(FunctionName, `factchecker`)].{Name:FunctionName,Runtime:Runtime,Memory:MemorySize,Timeout:Timeout,LastModified:LastModified}' \
    --output table

echo ""
echo "To view details of a specific function:"
echo "  aws lambda get-function --function-name factchecker-url-to-video --region $AWS_REGION"
echo ""
echo "To view logs:"
echo "  aws logs tail /aws/lambda/factchecker-url-to-video --follow --region $AWS_REGION"
echo ""
echo "To test the function:"
echo "  aws lambda invoke --function-name factchecker-url-to-video --payload '{}' response.json --region $AWS_REGION"

