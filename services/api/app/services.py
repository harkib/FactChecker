"""Business logic for the API service."""
import os
import sys

# Add shared directory to path
# From /app/app/services.py, go up one level to /app, then shared is at /app/shared
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from sqlalchemy.ext.asyncio import AsyncSession
from shared.database import create_job_async, get_job_async, update_job_status_async, get_jobs_by_client_id_async
from shared.logger import get_logger, bind_job_id

# Initialize logger with resource name
logger = get_logger("api")


async def create_fact_check_job(db: AsyncSession, video_url: str, client_id: str) -> str:
    """Create a new fact-checking job and send message to queue.
    
    Args:
        db: Database session
        video_url: URL of the video to process
        client_id: Client ID (IDFV from iOS app) - required
    """
    # Create job in database
    job_id = await create_job_async(db, video_url, client_id=client_id)
    job_logger = bind_job_id(logger, job_id)
    job_logger.debug("Job created in database")
    
    # Send message to url-to-video queue
    queue_url = os.getenv("URL_TO_VIDEO_QUEUE_URL")
    if not queue_url:
        job_logger.error("URL_TO_VIDEO_QUEUE_URL not configured")
        await update_job_status_async(db, job_id, "failed", "URL_TO_VIDEO_QUEUE_URL not configured")
        raise ValueError("URL_TO_VIDEO_QUEUE_URL not configured")
    
    from shared.sqs_client import send_message
    job_logger.debug("Sending message to url-to-video queue", queue_url=queue_url)
    message_sent = await send_message(queue_url, {
        "job_id": job_id,
        "video_url": video_url,
    })
    
    if not message_sent:
        job_logger.error("Failed to send message to queue")
        await update_job_status_async(db, job_id, "failed", "Failed to send message to queue")
        raise RuntimeError("Failed to send message to queue")
    
    job_logger.info("Message sent to url-to-video queue successfully")
    return job_id


async def get_job_by_id(db: AsyncSession, job_id: str):
    """Get job by ID."""
    job_logger = bind_job_id(logger, job_id)
    job_logger.debug("Retrieving job from database")
    return await get_job_async(db, job_id)


async def get_jobs_by_client_id(db: AsyncSession, client_id: str):
    """Get last 10 jobs by client_id, ordered by created_at descending.
    
    Args:
        db: Database session
        client_id: Client ID to filter by
        
    Returns:
        List of job dictionaries, ordered by created_at descending (most recent first)
    """
    logger.debug("Retrieving jobs from database", client_id=client_id)
    return await get_jobs_by_client_id_async(db, client_id, limit=10)

