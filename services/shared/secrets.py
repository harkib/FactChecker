"""Secrets management utilities for Lambda functions."""
import os
import json
import aioboto3


async def initialize_secrets():
    """Fetch secrets from Secrets Manager and set as environment variables."""
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
            try:
                openai_secret = await secrets_client.get_secret_value(SecretId=openai_secret_arn)
                openai_creds = json.loads(openai_secret['SecretString'])
                os.environ['OPENAI_API_KEY'] = openai_creds.get('OPENAI_API_KEY', '')
            except Exception as e:
                # Use print since logger might not be initialized yet
                print(f"Warning: Failed to fetch OpenAI secret: {e}")

