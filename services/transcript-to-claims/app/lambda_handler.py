"""Lambda handler for Transcript to Claims transformation (async)."""
import os
import json
import sys
import asyncio
from typing import Dict, Any, List

# Ensure /app is in Python path (fallback if PYTHONPATH env var isn't set)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

# Import modules that don't depend on secrets
from shared.logger import get_logger, bind_job_id
from shared.secrets import initialize_secrets
from shared.sqs_client import send_message
from shared.database import get_sessionmaker, update_job_status_async, update_job_failed_async, JobStatus
from app.processor import extract_claims

# Initialize logger with resource name
logger = get_logger("transcript-to-claims lambda")


def get_openai_api_key():
    """Get OpenAI API key from environment variable (injected by Lambda from Secrets Manager)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    return api_key


async def process_message(message_body: dict, session, next_queue_url: str) -> bool:
    """Process a single message (async)."""
    job_id = message_body.get("job_id")
    transcript_s3_key = message_body.get("transcript_s3_key")
    frames_s3_prefix = message_body.get("frames_s3_prefix")
    
    # Bind job_id to logger context
    job_logger = bind_job_id(logger, job_id) if job_id else logger
    
    if not job_id or not transcript_s3_key or not frames_s3_prefix:
        job_logger.warning("Invalid message: missing required fields")
        return False
    
    try:
        job_logger.info(
            "Processing job: extracting claims from transcript and frames",
            transcript_s3_key=transcript_s3_key,
            frames_s3_prefix=frames_s3_prefix
        )
        
        assets_bucket = os.getenv("ASSETS_BUCKET")
        if not assets_bucket:
            raise ValueError("ASSETS_BUCKET must be set")
        
        openai_api_key = get_openai_api_key()
        if not openai_api_key:
            raise ValueError("OpenAI API key not found")
        
        # Set status to EXTRACTING before starting claims extraction
        await update_job_status_async(session, job_id, JobStatus.EXTRACTING.value, None)
        
        claims, title = await extract_claims(
            job_id, transcript_s3_key, frames_s3_prefix, assets_bucket, openai_api_key, session
        )
        
        job_logger.info("Extracted claims", claims_count=len(claims), title=title)
        
        # Update job with claims and title (async) - sets status to CLAIMS_EXTRACTED
        from shared.database import update_job_claims_async
        await update_job_claims_async(session, job_id, claims, title)
        

        
        # Send message to next queue (claims-to-verified)
        if next_queue_url:
            await send_message(next_queue_url, {
                "job_id": job_id,
                "claims": claims,
            })
            job_logger.info("Sent message to claims-to-verified queue")
        else:
            job_logger.warning("CLAIMS_TO_VERIFIED_QUEUE_URL not configured")
        
        return True
    except Exception as e:
        job_logger.error("Error processing job", exc_info=True, error=str(e))
        # Mark job as failed
        await update_job_failed_async(session, job_id, True, str(e))
        return False


async def async_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Async Lambda handler for SQS event batches.
    
    Args:
        event: SQS event with Records array
        context: Lambda context
    
    Returns:
        Dict with batchItemFailures for partial batch processing
    """
    # Initialize secrets from Secrets Manager (must happen before using database)
    await initialize_secrets()
    
    batch_item_failures: List[Dict[str, str]] = []
    next_queue_url = os.getenv("CLAIMS_TO_VERIFIED_QUEUE_URL")
    
    # Process each record in the batch
    for record in event.get("Records", []):
        message_id = record.get("messageId", "")
        
        try:
            # Parse message body
            message_body = json.loads(record.get("body", "{}"))
            
            # Process message with its own database session
            async with get_sessionmaker()() as session:
                success = await process_message(message_body, session, next_queue_url)
                
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


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Synchronous wrapper for async handler.
    Lambda Runtime Interface Client requires a synchronous handler.
    """
    # Create a new event loop for each invocation to avoid loop conflicts
    # This ensures all async operations in this invocation use the same loop
    loop = None
    try:
        loop = asyncio.get_event_loop()
        logger.info("Using existing event loop")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.info("Created new event loop")
        
    return loop.run_until_complete(async_handler(event, context))