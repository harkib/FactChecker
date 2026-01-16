"""Lambda handler for URL to Video transformation (async)."""
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
from shared.database import get_sessionmaker, update_job_status_async
from app.processor import download_video

# Initialize logger with resource name
logger = get_logger("url-to-video lambda")


def _create_batch_failures(records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, str]]]:
    """Create batch item failures response from records."""
    return {
        "batchItemFailures": [
            {"itemIdentifier": record.get("messageId", "")}
            for record in records
        ]
    }


async def process_message(message_body: dict, session, next_queue_url: str, update_job_status_fn) -> bool:
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
        await update_job_status_fn(session, job_id, "failed", str(e))
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
    next_queue_url = os.getenv("VIDEO_TO_TRANSCRIPT_QUEUE_URL")
    
    # Process each record in the batch
    for record in event.get("Records", []):
        message_id = record.get("messageId", "")
        
        try:
            # Parse message body
            message_body = json.loads(record.get("body", "{}"))
            
            # Process message with its own database session
            async with get_sessionmaker()() as session:
                success = await process_message(message_body, session, next_queue_url, update_job_status_async)
                
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
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(async_handler(event, context))
    finally:
        loop.close()
        asyncio.set_event_loop(None)
