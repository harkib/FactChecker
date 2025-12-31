# FactChecker Infrastructure

This directory contains AWS CDK infrastructure definitions for the FactChecker application.

## Prerequisites

1. AWS CLI configured with appropriate credentials
2. AWS CDK CLI installed: `npm install -g aws-cdk`
3. Python 3.13
4. Docker (for building container images)

## Setup

1. Install Python dependencies:
```bash
cd infra
pip install -r requirements.txt
```

2. Bootstrap CDK (if not already done):
```bash
cdk bootstrap
```

3. Create the OpenAI API key secret in AWS Secrets Manager:
```bash
aws secretsmanager create-secret \
  --name factchecker/openai-api-key \
  --secret-string '{"OPENAI_API_KEY":"your-api-key-here"}'
```

## Deployment

1. Build and push Docker images to ECR (update ECR repository URLs in stacks first)

2. Deploy all stacks:
```bash
cdk deploy --all
```

Or deploy individual stacks:
```bash
cdk deploy StorageStack
cdk deploy DatabaseStack
cdk deploy QueueStack
cdk deploy ApiStack
cdk deploy WorkerStacks
```

## Database Schema

After deploying the database stack, connect to the database and run:

```sql
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_url TEXT NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    video_s3_key TEXT,
    transcript_s3_key TEXT,
    frames_s3_prefix TEXT,
    claims JSONB,
    verified_claims JSONB,
    error_message TEXT
);

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);
```

## Important Notes

- Update ECR repository URLs in `api_stack.py` and `worker_stacks.py` before deployment
- The database removal policy is set to DESTROY for development - change for production
- S3 buckets have auto-delete enabled for development - disable for production
- Configure appropriate VPC, security groups, and IAM permissions for production use
- Set up CloudWatch alarms and monitoring for production workloads

