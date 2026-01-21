#!/bin/bash
# Build script for Docker images
# Run from repository root
# Usage: ./build.sh [tag]
#   tag: Optional image tag (default: latest)

set -e

# Load environment variables if .env exists (optional, not required for building)
# Silently ignore .env file - build works without it
if [ -f .env ]; then
    set +e
    set -a
    source .env 2>/dev/null || true
    set +a
    set -e
fi

# Set defaults
AWS_REGION=${AWS_REGION:-"us-east-1"}

# Check AWS authentication
echo "Checking AWS authentication..."
if ! AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null); then
    echo "⚠️  WARNING: AWS authentication failed or expired. Please run 'aws configure' or refresh your credentials."
    echo "   Continuing with local build (images will be tagged as 'factchecker' instead of ECR path)..."
    AWS_ACCOUNT_ID=""
else
    echo "✓ AWS authenticated. Account ID: $AWS_ACCOUNT_ID"
fi

# Use provided ECR_REPO or construct from AWS_ACCOUNT_ID
if [ -z "$ECR_REPO" ] && [ -n "$AWS_ACCOUNT_ID" ]; then
    ECR_REPO="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/factchecker"
elif [ -z "$ECR_REPO" ]; then
    ECR_REPO="factchecker"  # Local build without ECR
fi

SERVICES=("api" "url-to-video" "video-to-transcript" "transcript-to-claims" "claims-to-verified" "transcript-to-verified")
IMAGE_TAG=${1:-"latest"}
PLATFORM="linux/amd64"

echo "Building Docker images for platform: $PLATFORM..."
echo "Repository: $ECR_REPO"
echo "Tag: $IMAGE_TAG"
echo ""

for service in "${SERVICES[@]}"; do
    echo "Building $service:$IMAGE_TAG for $PLATFORM..."
    docker build --platform $PLATFORM --provenance=false -f services/$service/Dockerfile -t $ECR_REPO/$service:$IMAGE_TAG .
    echo "✓ Built $service:$IMAGE_TAG"
    echo ""
done

echo "All services built successfully!"
echo ""
if [ -n "$AWS_ACCOUNT_ID" ]; then
    echo "To push to ECR, run:"
    echo "  ./push.sh $IMAGE_TAG"
    echo ""
    echo "Or manually:"
    echo "  aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
    for service in "${SERVICES[@]}"; do
        echo "  docker push $ECR_REPO/$service:$IMAGE_TAG"
    done
else
    echo "Note: AWS_ACCOUNT_ID not set. Images built locally only."
    echo "Set AWS_ACCOUNT_ID or ECR_REPO to build for ECR."
fi

