#!/bin/bash
# Force update all Lambda functions with new ECR images
# Run from infra directory

set -e

REGION=${AWS_REGION:-"us-east-1"}

# List of all Lambda service names
SERVICES=(
    # "url-to-video"
    # "video-to-transcript"
    "transcript-to-verified"
    # "s3-video-event"
)

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "Updating all Lambda functions..."
echo "Region: $REGION"
echo "AWS Account: $AWS_ACCOUNT_ID"
echo ""

# Update each Lambda function
for service_name in "${SERVICES[@]}"; do
    FUNCTION_NAME="factchecker-$service_name"
    ECR_REPO="$AWS_ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/factchecker/$service_name"
    
    echo "=========================================="
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
    echo "✓ Lambda function $FUNCTION_NAME updated successfully!"
    echo ""
done

echo "=========================================="
echo "All Lambda functions updated!"
echo ""
echo "Checking status of all functions..."
echo ""

# Check status of all functions
for service_name in "${SERVICES[@]}"; do
    FUNCTION_NAME="factchecker-$service_name"
    echo "--- $FUNCTION_NAME ---"
    aws lambda get-function-configuration \
        --function-name $FUNCTION_NAME \
        --region $REGION \
        --query '{LastUpdateStatus:LastUpdateStatus,LastUpdateStatusReason:LastUpdateStatusReason}' \
        --output table
    echo ""
done