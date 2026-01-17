"""Secrets management utilities for Lambda functions."""
import os
import json
import aioboto3

secrets_initialized = False

async def initialize_secrets():
    global secrets_initialized
    """Fetch secrets from Secrets Manager and set as environment variables."""
    if secrets_initialized:
        return
    
    session = aioboto3.Session()
    async with session.client('secretsmanager', region_name=os.getenv('AWS_REGION', 'us-east-1')) as secrets_client:
        # Fetch database secret
        db_secret_arn = os.getenv('DB_SECRET_ARN')
        if db_secret_arn and not os.getenv('DB_USER'):
            try:
                db_secret = await secrets_client.get_secret_value(SecretId=db_secret_arn)
                db_creds = json.loads(db_secret['SecretString'])
                os.environ['DB_USER'] = db_creds.get('username', 'postgres')
                os.environ['DB_PASSWORD'] = db_creds.get('password', '')
            except Exception as e:
                # Use print since logger might not be initialized yet
                print(f"Warning: Failed to fetch database secret: {e}")
        
        # Fetch OpenAI secret
        openai_secret_arn = os.getenv('OPENAI_SECRET_ARN')
        if openai_secret_arn and not os.getenv('OPENAI_API_KEY'):
            aws_region = os.getenv('AWS_REGION', 'us-east-1')
            try:
                openai_secret = await secrets_client.get_secret_value(SecretId=openai_secret_arn)
                openai_creds = json.loads(openai_secret['SecretString'])
                openai_api_key = openai_creds.get('OPENAI_API_KEY', '')
                
                # Validate that OPENAI_API_KEY exists and is not empty
                if not openai_api_key:
                    raise ValueError(
                        f"OPENAI_API_KEY field is missing or empty in secret {openai_secret_arn}. "
                        f"Region: {aws_region}. Secret keys available: {list(openai_creds.keys())}"
                    )
                
                os.environ['OPENAI_API_KEY'] = openai_api_key
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Failed to parse OpenAI secret JSON from {openai_secret_arn}. "
                    f"Region: {aws_region}. Error: {str(e)}"
                ) from e
            except Exception as e:
                # Raise exception with detailed context instead of silently continuing
                error_type = type(e).__name__
                raise RuntimeError(
                    f"Failed to fetch OpenAI secret {openai_secret_arn}. "
                    f"Region: {aws_region}. Error type: {error_type}. Error: {str(e)}"
                ) from e
                
    secrets_initialized = True

