# CDK Deployment Guide

## Quick Start

### Deploy All Stacks
```bash
cd infra
cdk deploy --all
```

### Deploy Individual Stack
```bash
cd infra
cdk deploy EcrStack        # ECR repositories
cdk deploy StorageStack    # S3 buckets
cdk deploy DatabaseStack   # RDS database
cdk deploy QueueStack      # SQS queues
cdk deploy ApiStack        # REST API service
cdk deploy WorkerStacks    # Worker services
```

## Deployment Process

### 1. First Time Setup

```bash
cd infra

# Install Python dependencies
pip3 install -r requirements.txt

# Bootstrap CDK (only needed once per account/region)
cdk bootstrap

# Create OpenAI secret in Secrets Manager
aws secretsmanager create-secret \
  --name factchecker/openai-api-key \
  --secret-string '{"OPENAI_API_KEY":"your-api-key-here"}' \
  --region us-east-1
```

### 2. Deploy Infrastructure

CDK will show you a summary of resources to be created and ask for confirmation:

```bash
cdk deploy --all
```

You'll see output like:
```
Stack EcrStack
  Resources
    + AWS::ECR::Repository ApiRepository factchecker/api
    + AWS::ECR::Repository UrlToVideoRepository factchecker/url-to-video
    ...

Do you wish to deploy these changes (y/n)?
```

**Type `y` and press Enter** to confirm and proceed with deployment.

### 3. Deployment Order

CDK automatically handles dependencies, but recommended order:

1. **EcrStack** - Creates ECR repositories (needed for images)
2. **StorageStack** - Creates S3 buckets
3. **DatabaseStack** - Creates RDS database
4. **QueueStack** - Creates SQS queues
5. **ApiStack** - Creates API service (depends on above)
6. **WorkerStacks** - Creates worker services (depends on above)

Or simply deploy all at once:
```bash
cdk deploy --all
```

## Common Commands

### List All Stacks
```bash
cdk list
```

### View Changes Before Deploying
```bash
cdk diff
```

### Synthesize CloudFormation Templates
```bash
cdk synth
```

### Destroy All Resources
```bash
cdk destroy --all
```

**Warning:** This will delete all resources. Make sure you have backups!

## Troubleshooting

### "python: command not found"

The `cdk.json` file uses `python3` by default. If you still see this error:

1. Check if Python 3 is installed:
   ```bash
   python3 --version
   ```

2. If not installed, install it:
   ```bash
   # macOS
   brew install python3
   
   # Or use system Python
   which python3
   ```

3. Update `cdk.json` if needed:
   ```json
   "app": "python3 app.py"
   ```

### "Stack not found"

Make sure you're using the correct stack name. List available stacks:
```bash
cdk list
```

Stack names are:
- `EcrStack`
- `StorageStack`
- `DatabaseStack`
- `QueueStack`
- `ApiStack`
- `WorkerStacks`

### "Cannot find module"

Install CDK dependencies:
```bash
cd infra
pip3 install -r requirements.txt
```

### Deployment Fails

1. Check AWS credentials:
   ```bash
   aws sts get-caller-identity
   ```

2. Check CloudFormation console for detailed error messages

3. Review CDK output for specific errors

### Acknowledge CDK Notices

To stop seeing telemetry notices:
```bash
cdk acknowledge 34892
```

## Environment Variables

You can set CDK environment variables:

```bash
export CDK_DEFAULT_ACCOUNT=123456789012
export CDK_DEFAULT_REGION=us-east-1

cdk deploy --all
```

Or use CDK context:
```bash
cdk deploy --all --context account=123456789012 --context region=us-east-1
```

## After Deployment

1. **Get API endpoint:**
   ```bash
   aws cloudformation describe-stacks \
     --stack-name ApiStack \
     --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDNS`].OutputValue' \
     --output text
   ```

2. **Check ECR repositories:**
   ```bash
   aws ecr describe-repositories --repository-names factchecker/api
   ```

3. **Build and push images:**
   ```bash
   cd ..
   ./build.sh
   ./push.sh
   ```

4. **Run database migrations:**
   Connect to RDS and run the SQL from `infra/README.md`

## Best Practices

1. **Always review changes** with `cdk diff` before deploying
2. **Use stack names** not file paths when deploying
3. **Deploy in order** or use `--all` to let CDK handle dependencies
4. **Keep secrets in Secrets Manager**, not in code
5. **Use version tags** for production deployments
6. **Test in dev/staging** before production

