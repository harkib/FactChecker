#!/bin/bash
# Force update Lambda function with new ECR image
# Run from infra directory

set -e

FUNCTION_NAME="factchecker-url-to-video"
REGION=${AWS_REGION:-"us-east-1"}

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="$AWS_ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/factchecker/url-to-video"

echo "Updating Lambda function: $FUNCTION_NAME"
echo "Image: $ECR_REPO:latest"
echo ""

# Update the Lambda function code
aws lambda update-function-code \
    --function-name $FUNCTION_NAME \
    --image-uri "$ECR_REPO:latest" \
    --region $REGION

echo ""
echo "Waiting for update to complete..."
aws lambda wait function-updated \
    --function-name $FUNCTION_NAME \
    --region $REGION

echo ""
echo "✓ Lambda function updated successfully!"
echo ""
echo "Check status:"
aws lambda get-function-configuration \
    --function-name $FUNCTION_NAME \
    --region $REGION \
    --query '{LastUpdateStatus:LastUpdateStatus,LastUpdateStatusReason:LastUpdateStatusReason}' \
    --output table

