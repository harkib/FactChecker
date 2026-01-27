"""Lambda handler for S3 video upload events (async)."""
import os
import json
import sys
import asyncio
import re
from typing import Dict, Any, List

# Ensure /app is in Python path (fallback if PYTHONPATH env var isn't set)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

# Import modules that don't depend on secrets
from shared.logger import get_logger, bind_job_id
from shared.secrets import initialize_secrets
from shared.sqs_client import send_message
from shared.database import get_sessionmaker, update_job_video_s3_key_async, JobStatus

# Initialize logger with resource name
logger = get_logger("s3-video-event lambda")


def extract_job_id_from_s3_key(s3_key: str) -> str:
    """Extract job_id from S3 key.
    
    Expected format: videos/{job_id}.mp4
    
    Args:
        s3_key: S3 key of the uploaded video
        
    Returns:
        Job ID string
    """
    # Match pattern: videos/{job_id}.mp4
    match = re.match(r'videos/([^/]+)\.mp4$', s3_key)
    if match:
        return match.group(1)
    raise ValueError(f"Unable to extract job_id from S3 key: {s3_key}")


async def process_s3_event(record: Dict[str, Any], video_to_transcript_queue_url: str) -> bool:
    """Process a single S3 event record (async).
    
    Args:
        record: S3 event record
        video_to_transcript_queue_url: URL of video-to-transcript queue
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Extract S3 event details
        s3_info = record.get("s3", {})
        bucket_name = s3_info.get("bucket", {}).get("name")
        s3_key = s3_info.get("object", {}).get("key")
        
        # URL decode the S3 key (S3 events encode special characters)
        if s3_key:
            import urllib.parse
            s3_key = urllib.parse.unquote_plus(s3_key)
        
        if not s3_key:
            logger.warning("S3 event missing object key", record=record)
            return False
        
        logger.info("Processing S3 video upload event", bucket=bucket_name, key=s3_key)
        
        # Extract job_id from S3 key
        try:
            job_id = extract_job_id_from_s3_key(s3_key)
        except ValueError as e:
            logger.warning("Failed to extract job_id from S3 key", s3_key=s3_key, error=str(e))
            return False
        
        job_logger = bind_job_id(logger, job_id)
        job_logger.info("Extracted job_id from S3 key", s3_key=s3_key)
        
        # Update job with video S3 key and mark as downloaded
        async with get_sessionmaker()() as session:
            await update_job_video_s3_key_async(session, job_id, s3_key)
            job_logger.info("Updated job with video S3 key", status=JobStatus.DOWNLOADED.value)
        
        # Send message to video-to-transcript queue
        if video_to_transcript_queue_url:
            await send_message(video_to_transcript_queue_url, {
                "job_id": job_id,
                "video_s3_key": s3_key,
            })
            job_logger.info("Sent message to video-to-transcript queue")
        else:
            job_logger.warning("VIDEO_TO_TRANSCRIPT_QUEUE_URL not configured")
        
        return True
        
    except Exception as e:
        logger.error("Error processing S3 event", exc_info=True, error=str(e), record=record)
        return False


async def async_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Async Lambda handler for S3 event notifications.
    
    Args:
        event: S3 event with Records array
        context: Lambda context
    
    Returns:
        Dict with processing results
    """
    # Initialize secrets from Secrets Manager (must happen before using database)
    await initialize_secrets()
    
    video_to_transcript_queue_url = os.getenv("VIDEO_TO_TRANSCRIPT_QUEUE_URL")
    if not video_to_transcript_queue_url:
        logger.error("VIDEO_TO_TRANSCRIPT_QUEUE_URL not configured")
        return {"error": "VIDEO_TO_TRANSCRIPT_QUEUE_URL not configured"}
    
    success_count = 0
    failure_count = 0
    
    # Process each S3 event record
    for record in event.get("Records", []):
        try:
            success = await process_s3_event(record, video_to_transcript_queue_url)
            if success:
                success_count += 1
            else:
                failure_count += 1
        except Exception as e:
            logger.error("Error processing S3 event record", exc_info=True, error=str(e), record=record)
            failure_count += 1
    
    logger.info("Processed S3 events", success=success_count, failures=failure_count)
    return {
        "success": success_count,
        "failures": failure_count,
        "total": len(event.get("Records", []))
    }


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Synchronous wrapper for async handler.
    Lambda Runtime Interface Client requires a synchronous handler.
    """
    # Create a new event loop for each invocation to avoid loop conflicts
    loop = None
    try:
        loop = asyncio.get_event_loop()
        logger.info("Using existing event loop")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.info("Created new event loop")
        
    return loop.run_until_complete(async_handler(event, context))
