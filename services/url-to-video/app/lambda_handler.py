"""Lambda handler for URL to Video transformation (async)."""
import os
import json
import sys
import asyncio
import aioboto3
from typing import Dict, Any, List

# Ensure /app is in Python path (fallback if PYTHONPATH env var isn't set)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

# Import modules that don't depend on secrets
from shared.logger import get_logger, bind_job_id

# Initialize logger with resource name
logger = get_logger("url-to-video lambda")

# Module-level flag to track if secrets and database are initialized
_secrets_initialized = False
_database_initialized = False


async def _initialize_secrets():
    """Fetch secrets from Secrets Manager and set as environment variables."""
    global _secrets_initialized
    if _secrets_initialized:
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
                logger.warning("Failed to fetch database secret", error=str(e))
        
        # Fetch OpenAI secret
        openai_secret_arn = os.getenv('OPENAI_SECRET_ARN')
        if openai_secret_arn and not os.getenv('OPENAI_API_KEY'):
            try:
                openai_secret = await secrets_client.get_secret_value(SecretId=openai_secret_arn)
                openai_creds = json.loads(openai_secret['SecretString'])
                os.environ['OPENAI_API_KEY'] = openai_creds.get('OPENAI_API_KEY', '')
            except Exception as e:
                logger.warning("Failed to fetch OpenAI secret", error=str(e))
    
    _secrets_initialized = True


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Synchronous wrapper for async handler.
    Lambda Runtime Interface Client requires a synchronous handler.
    """
    return asyncio.run(async_handler(event, context))


async def async_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Async Lambda handler for SQS event batches.
    
    Args:
        event: SQS event with Records array
        context: Lambda context
    
    Returns:
        Dict with batchItemFailures for partial batch processing
    """
    global _database_initialized
    
    # Initialize secrets from Secrets Manager (must happen before importing database)
    await _initialize_secrets()
    
    # Import database and other modules after secrets are set
    from shared.sqs_client import send_message
    from shared.database import init_db, sessionmaker, update_job_status_async
    from app.processor import download_video
    
    # Initialize database on first invocation
    if not _database_initialized:
        try:
            await init_db()
            _database_initialized = True
        except Exception as e:
            logger.error("Failed to initialize database", exc_info=True, error=str(e))
            # Return all message IDs as failures
            if "Records" in event:
                return {
                    "batchItemFailures": [
                        {"itemIdentifier": record.get("messageId", "")}
                        for record in event["Records"]
                    ]
                }
            return {"batchItemFailures": []}
    
    # Verify database initialization completed
    if sessionmaker is None:
        logger.error("Database initialization failed: sessionmaker is None")
        if "Records" in event:
            return {
                "batchItemFailures": [
                    {"itemIdentifier": record.get("messageId", "")}
                    for record in event["Records"]
                ]
            }
        return {"batchItemFailures": []}
    
    async def process_message(message_body: dict, session) -> bool:
        """Process a single message (async)."""
        job_id = message_body.get("job_id")
        video_url = message_body.get("video_url")
        
        # Bind job_id to logger context
        job_logger = bind_job_id(logger, job_id) if job_id else logger
        
        if not job_id or not video_url:
            job_logger.warning("Invalid message: missing job_id or video_url")
            return False
        
        try:
            job_logger.info("Processing job: downloading video", video_url=video_url)
            s3_key = await download_video(video_url, job_id, session)
            job_logger.info("Successfully downloaded and uploaded video", s3_key=s3_key)
            
            # Send message to next queue (video-to-transcript)
            next_queue_url = os.getenv("VIDEO_TO_TRANSCRIPT_QUEUE_URL")
            if next_queue_url:
                await send_message(next_queue_url, {
                    "job_id": job_id,
                    "video_s3_key": s3_key,
                })
                job_logger.info("Sent message to video-to-transcript queue")
            else:
                job_logger.warning("VIDEO_TO_TRANSCRIPT_QUEUE_URL not configured")
            
            return True
        except Exception as e:
            job_logger.error("Error processing job", exc_info=True, error=str(e))
            await update_job_status_async(session, job_id, "failed", str(e))
            return False
    
    batch_item_failures: List[Dict[str, str]] = []
    
    # Process each record in the batch
    for record in event.get("Records", []):
        message_id = record.get("messageId", "")
        receipt_handle = record.get("receiptHandle", "")
        
        try:
            # Parse message body
            message_body = json.loads(record.get("body", "{}"))
            
            # Process message with its own database session
            async with sessionmaker() as session:
                success = await process_message(message_body, session)
                
                if not success:
                    # Add to batch failures for retry
                    batch_item_failures.append({"itemIdentifier": message_id})
                    logger.warning("Failed to process message", message_id=message_id)
                else:
                    logger.info("Successfully processed message", message_id=message_id)
                    
        except json.JSONDecodeError as e:
            logger.error("Error decoding message", exc_info=True, error=str(e), message_id=message_id)
            # Invalid JSON - add to failures
            batch_item_failures.append({"itemIdentifier": message_id})
        except Exception as e:
            logger.error("Error processing message", exc_info=True, error=str(e), message_id=message_id)
            # Processing error - add to failures
            batch_item_failures.append({"itemIdentifier": message_id})
    
    # Return batch item failures for partial batch processing
    return {"batchItemFailures": batch_item_failures}
