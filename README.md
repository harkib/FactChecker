# FactChecker

A production-ready fact-checking application for short social media videos, built with microservices architecture on AWS.

## Architecture

The application consists of:

1. **REST API Service** - FastAPI service that accepts video URLs and returns fact-checking results
2. **URL-to-Video Worker** - Downloads videos from URLs and stores them in S3
3. **Video-to-Transcript Worker** - Extracts audio, transcribes with Whisper, and extracts key frames
4. **Transcript-to-Claims Worker** - Extracts factual claims from transcript and frames using OpenAI
5. **Claims-to-Verified Worker** - Verifies claims using OpenAI

## Repository Structure

```
FactChecker/
├── services/          # Microservices
│   ├── api/           # REST API service
│   ├── url-to-video/  # Video download worker
│   ├── video-to-transcript/  # Video processing worker
│   ├── transcript-to-claims/  # Claim extraction worker
│   ├── claims-to-verified/  # Claim verification worker
│   └── shared/        # Shared utilities
├── infra/             # AWS CDK infrastructure definitions
└── ios/              # iOS app (empty for now)
```

## Prerequisites

- Python 3.13
- AWS CLI configured
- AWS CDK CLI installed
- Docker
- ffmpeg (for local development)

## Local Development

### Setup

1. Install dependencies for each service:
```bash
cd services/api && pip install -r requirements.txt
cd ../url-to-video && pip install -r requirements.txt
# ... repeat for other services
```

2. Set up environment variables:
```bash
export OPENAI_API_KEY=your-key-here
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=factchecker
export DB_USER=postgres
export DB_PASSWORD=your-password
```

3. Run the API service locally:
```bash
cd services/api
uvicorn app.main:app --reload
```

### Running Workers Locally

Workers can be run locally for testing, but they require:
- SQS queues configured
- S3 buckets configured
- Database access

See individual service READMEs for more details.

## Deployment

### Infrastructure

1. Navigate to infrastructure directory:
```bash
cd infra
```

2. Install CDK dependencies:
```bash
pip install -r requirements.txt
```

3. Create OpenAI secret in AWS Secrets Manager:
```bash
aws secretsmanager create-secret \
  --name factchecker/openai-api-key \
  --secret-string '{"OPENAI_API_KEY":"your-api-key-here"}'
```

4. Bootstrap CDK (if not already done):
```bash
cdk bootstrap
```

5. Deploy infrastructure:
```bash
cdk deploy --all
```

### Services

1. Build and push Docker images to ECR (update ECR repository URLs in CDK stacks first)

2. Deploy services (handled by CDK):
```bash
cdk deploy ApiStack WorkerStacks
```

## Database Schema

After deploying, connect to the RDS database and run:

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

## API Endpoints

- `POST /jobs` - Create a new fact-checking job
  - Request: `{"video_url": "https://..."}`
  - Response: `{"job_id": "...", "status": "pending"}`

- `GET /jobs/{job_id}` - Get job status
  - Response: Job object with current status

- `GET /jobs/{job_id}/results` - Get verified claims (only when completed)
  - Response: Job object with verified_claims

- `GET /health` - Health check endpoint

## Environment Variables

### API Service
- `DB_HOST` - Database hostname
- `DB_PORT` - Database port (default: 5432)
- `DB_NAME` - Database name
- `DB_USER` - Database username (from Secrets Manager)
- `DB_PASSWORD` - Database password (from Secrets Manager)
- `VIDEO_BUCKET` - S3 bucket for videos
- `ASSETS_BUCKET` - S3 bucket for transcripts and frames
- `URL_TO_VIDEO_QUEUE_URL` - SQS queue URL
- `AWS_REGION` - AWS region
- `OPENAI_SECRET_NAME` - Secrets Manager secret name for OpenAI API key

### Workers
- Same database variables as API
- Service-specific queue URLs
- `OPENAI_SECRET_NAME` - For OpenAI workers

## Notes

- The infrastructure is configured for development (auto-delete S3 objects, destroyable RDS)
- Update removal policies and security settings for production
- Configure appropriate VPC, security groups, and IAM permissions
- Set up CloudWatch alarms and monitoring
- Update ECR repository URLs in CDK stacks before deployment
