"""Business logic for the API service."""
import os
import sys

# Add shared directory to path
# From /app/app/services.py, go up one level to /app, then shared is at /app/shared
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from shared.database import create_job, get_job, update_job_status
from shared.sqs_client import send_message


def create_fact_check_job(video_url: str) -> str:
    """Create a new fact-checking job and send message to queue."""
    # Create job in database
    job_id = create_job(video_url)
    
    # Send message to url-to-video queue
    queue_url = os.getenv("URL_TO_VIDEO_QUEUE_URL")
    if not queue_url:
        update_job_status(job_id, "failed", "URL_TO_VIDEO_QUEUE_URL not configured")
        raise ValueError("URL_TO_VIDEO_QUEUE_URL not configured")
    
    message_sent = send_message(queue_url, {
        "job_id": job_id,
        "video_url": video_url,
    })
    
    if not message_sent:
        update_job_status(job_id, "failed", "Failed to send message to queue")
        raise RuntimeError("Failed to send message to queue")
    
    return job_id


def get_job_by_id(job_id: str):
    """Get job by ID."""
    return get_job(job_id)

