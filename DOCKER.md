# Docker Image Management Guide

This guide walks you through building, tagging, and pushing Docker images for all FactChecker services to AWS ECR (Elastic Container Registry).

## Overview

The FactChecker application consists of 5 services, each requiring a Docker image:
1. **api** - REST API service (FastAPI)
2. **url-to-video** - Video download worker
3. **video-to-transcript** - Video processing worker
4. **transcript-to-claims** - Claim extraction worker
5. **claims-to-verified** - Claim verification worker

## Prerequisites

1. **Docker installed** and running
2. **AWS CLI configured** with appropriate credentials
3. **AWS account** with permissions to:
   - Create ECR repositories
   - Push images to ECR
   - Deploy ECS services

## Step 1: Set Up ECR Repositories

ECR repositories are now managed by CDK! When you deploy the infrastructure, the ECR stack will automatically create all required repositories.

### Using CDK (Recommended)

The ECR repositories are defined in `infra/stacks/ecr_stack.py` and will be created automatically when you deploy:

```bash
cd infra
cdk deploy EcrStack
```

Or deploy all stacks:
```bash
cdk deploy --all
```

This creates:
- `factchecker/api`
- `factchecker/url-to-video`
- `factchecker/video-to-transcript`
- `factchecker/transcript-to-claims`
- `factchecker/claims-to-verified`

### Manual Setup (Alternative)

If you prefer to create repositories manually, you can use the `setup-ecr.sh` script:

```bash
./setup-ecr.sh
```

**Note:** If you create repositories manually, make sure they match the names expected by CDK (`factchecker/<service-name>`).

## Step 2: Configure Build Script

The build script (`build.sh`) needs to know your ECR repository details:

```bash
# Set environment variables
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export ECR_REPO=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/factchecker
```

Or create a `.env` file:
```bash
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012
ECR_REPO=123456789012.dkr.ecr.us-east-1.amazonaws.com/factchecker
```

## Step 3: Build Docker Images

### Build All Services

```bash
# From repository root
./build.sh
```

This builds all services with the `latest` tag.

### Build Individual Service

```bash
docker build -f services/api/Dockerfile -t $ECR_REPO/api:latest .
```

### Build with Version Tag

For production, use version tags:

```bash
VERSION=v1.0.0
./build.sh $VERSION
```

## Step 4: Authenticate Docker with ECR

Before pushing images, authenticate Docker with ECR:

```bash
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
```

This command is valid for 12 hours.

## Step 5: Push Images to ECR

### Push All Images

```bash
./push.sh
```

### Push Individual Image

```bash
docker push $ECR_REPO/api:latest
```

### Push with Version Tag

```bash
VERSION=v1.0.0
docker push $ECR_REPO/api:$VERSION
```

## Step 6: CDK Infrastructure

The CDK infrastructure is already configured to use ECR repositories! The `EcrStack` creates all repositories, and both `ApiStack` and `WorkerStacks` automatically reference them.

### How It Works

1. **EcrStack** (`infra/stacks/ecr_stack.py`):
   - Creates all 5 ECR repositories
   - Configures image scanning on push
   - Sets up lifecycle policies (keeps last 10 images, expires untagged images after 7 days)

2. **ApiStack** and **WorkerStacks**:
   - Automatically reference the ECR repositories created by EcrStack
   - Use `ecs.ContainerImage.from_ecr_repository()` to pull images

### Deployment Order

When deploying, CDK will automatically:
1. Create ECR repositories first (EcrStack)
2. Create ECS services that reference those repositories (ApiStack, WorkerStacks)

No manual configuration needed!

## Image Tagging Strategy

### Development
- Use `latest` tag for active development
- Images are overwritten on each push

### Staging/Production
- Use semantic versioning: `v1.0.0`, `v1.0.1`, etc.
- Use git commit SHA: `git-abc1234`
- Use date-based tags: `2024-01-15`

Example:
```bash
# Build with multiple tags
docker build -f services/api/Dockerfile \
    -t $ECR_REPO/api:latest \
    -t $ECR_REPO/api:v1.0.0 \
    -t $ECR_REPO/api:$(git rev-parse --short HEAD) \
    .

# Push all tags
docker push $ECR_REPO/api:latest
docker push $ECR_REPO/api:v1.0.0
docker push $ECR_REPO/api:$(git rev-parse --short HEAD)
```

## Image Optimization

### Multi-stage Builds (Optional)

For smaller images, consider multi-stage builds in Dockerfiles:

```dockerfile
# Build stage
FROM python:3.13-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.13-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY app/ ./app/
ENV PATH=/root/.local/bin:$PATH
CMD ["python", "app/main.py"]
```

### .dockerignore

Create `.dockerignore` in repository root:

```
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info
dist/
build/
.git/
.gitignore
.env
*.md
data/
downloads/
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Build and Push Docker Images

on:
  push:
    branches: [main]

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      
      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v1
      
      - name: Build and push
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          ECR_REPOSITORY: factchecker/api
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -f services/api/Dockerfile -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
```

## Troubleshooting

### Build Fails: "Cannot find shared directory"

The Dockerfiles expect the build context to be the repository root. Always build from root:
```bash
cd /path/to/FactChecker
docker build -f services/api/Dockerfile -t api:latest .
```

### Push Fails: "no basic auth credentials"

Re-authenticate with ECR:
```bash
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
```

### ECS Task Fails: "CannotPullContainerError"

1. Verify image exists in ECR:
   ```bash
   aws ecr describe-images --repository-name factchecker/api --region $AWS_REGION
   ```

2. Check ECS task execution role has ECR permissions (should be automatic with CDK)

3. Verify image tag matches CDK configuration

## Useful Commands

### List Images in ECR
```bash
aws ecr list-images --repository-name factchecker/api --region $AWS_REGION
```

### Delete Old Images
```bash
# List all images
aws ecr list-images --repository-name factchecker/api --region $AWS_REGION

# Delete specific image
aws ecr batch-delete-image \
    --repository-name factchecker/api \
    --image-ids imageTag=old-tag \
    --region $AWS_REGION
```

### View Image Details
```bash
docker inspect $ECR_REPO/api:latest
```

### Test Image Locally
```bash
docker run -p 8000:8000 \
    -e DB_HOST=localhost \
    -e DB_NAME=factchecker \
    -e DB_USER=postgres \
    -e DB_PASSWORD=password \
    $ECR_REPO/api:latest
```

## Next Steps

1. Set up ECR repositories
2. Update build script with your ECR details
3. Build and push images
4. Update CDK stacks to reference ECR repositories
5. Deploy infrastructure

