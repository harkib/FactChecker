"""Business logic for the API service."""
import os
import sys
from typing import Optional

# Add shared directory to path
# From /app/app/services.py, go up one level to /app, then shared is at /app/shared
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from sqlalchemy.ext.asyncio import AsyncSession
from shared.database import create_job_async, get_job_async, update_job_status_async, get_jobs_by_client_id_async, JobStatus
from shared.logger import get_logger, bind_job_id
import aioboto3
from botocore.exceptions import ClientError

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
        await update_job_status_async(db, job_id, JobStatus.FAILED.value, "URL_TO_VIDEO_QUEUE_URL not configured")
        raise ValueError("URL_TO_VIDEO_QUEUE_URL not configured")
    
    from shared.sqs_client import send_message
    job_logger.debug("Sending message to url-to-video queue", queue_url=queue_url)
    message_sent = await send_message(queue_url, {
        "job_id": job_id,
        "video_url": video_url,
    })
    
    if not message_sent:
        job_logger.error("Failed to send message to queue")
        await update_job_status_async(db, job_id, JobStatus.FAILED.value, "Failed to send message to queue")
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


async def generate_presigned_frame_url(bucket_name: str, frame_key: str, expiration: int = 3600) -> Optional[str]:
    """Generate a presigned URL for an S3 frame object.
    
    Args:
        bucket_name: Name of the S3 bucket
        frame_key: S3 key of the frame object
        expiration: URL expiration time in seconds (default: 1 hour)
        
    Returns:
        Presigned URL string or None if generation fails
    """
    try:
        session = aioboto3.Session()
        async with session.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1")) as s3_client:
            # Generate presigned URL for GET operation
            url = await s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket_name, "Key": frame_key},
                ExpiresIn=expiration
            )
            return url
    except ClientError as e:
        logger.error("Error generating presigned URL", bucket=bucket_name, key=frame_key, error=str(e))
        return None
    except Exception as e:
        logger.error("Unexpected error generating presigned URL", bucket=bucket_name, key=frame_key, error=str(e))
        return None

