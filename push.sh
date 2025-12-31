#!/bin/bash
# Push script for Docker images to ECR
# Run from repository root

set -e

# Load environment variables if .env exists (optional, not required for pushing)
if [ -f .env ]; then
    set +e  # Don't fail on errors
    set -a
    source .env 2>/dev/null || true
    set +a
    set -e  # Re-enable error handling
fi

# Set defaults
AWS_REGION=${AWS_REGION:-"us-east-1"}
AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text 2>/dev/null)}

if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo "Error: AWS_ACCOUNT_ID not set and cannot be determined from AWS CLI"
    echo "Please set AWS_ACCOUNT_ID environment variable or configure AWS CLI"
    exit 1
fi

ECR_REPO=${ECR_REPO:-"$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/factchecker"}

SERVICES=("api" "url-to-video" "video-to-transcript" "transcript-to-claims" "claims-to-verified")
IMAGE_TAG=${1:-"latest"}

echo "Pushing images to ECR..."
echo "Repository: $ECR_REPO"
echo "Tag: $IMAGE_TAG"
echo ""

# Authenticate Docker with ECR
echo "Authenticating with ECR..."
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Push each service
for service in "${SERVICES[@]}"; do
    echo "Pushing $service:$IMAGE_TAG..."
    docker push $ECR_REPO/$service:$IMAGE_TAG
    echo "Pushed $service:$IMAGE_TAG"
    echo ""
done

echo "All images pushed successfully!"
echo ""
echo "To verify, run:"
echo "  aws ecr list-images --repository-name factchecker/api --region $AWS_REGION"

