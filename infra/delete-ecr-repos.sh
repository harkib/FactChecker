#!/bin/bash
# Delete ECR repositories that were created during failed deployment
# Run from repository root

set -e

# Load environment variables if .env exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

AWS_REGION=${AWS_REGION:-"us-east-1"}
SERVICES=("api" "url-to-video" "video-to-transcript" "transcript-to-claims" "claims-to-verified")

echo "Deleting ECR repositories in region: $AWS_REGION"
echo ""

for service in "${SERVICES[@]}"; do
    repo_name="factchecker/$service"
    echo "Deleting repository: $repo_name"
    
    # Check if repository exists
    if aws ecr describe-repositories --repository-names $repo_name --region $AWS_REGION &>/dev/null; then
        # Delete all images first (required before deleting repository)
        echo "  Deleting all images in $repo_name..."
        aws ecr list-images --repository-name $repo_name --region $AWS_REGION --query 'imageIds[*]' --output json | \
            jq -r '.[] | "\(.imageDigest)"' | \
            while read digest; do
                if [ -n "$digest" ]; then
                    aws ecr batch-delete-image \
                        --repository-name $repo_name \
                        --image-ids imageDigest=$digest \
                        --region $AWS_REGION &>/dev/null || true
                fi
            done
        
        # Delete the repository
        aws ecr delete-repository \
            --repository-name $repo_name \
            --region $AWS_REGION \
            --force \
            --output json | jq -r '.repository.repositoryName' || true
        
        echo "  ✓ Deleted $repo_name"
    else
        echo "  Repository $repo_name does not exist, skipping..."
    fi
    echo ""
done

echo "All repositories deleted successfully!"

