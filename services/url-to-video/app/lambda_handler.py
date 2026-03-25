"""Lambda handler for URL to Video transformation (async)."""
import sys

# Ensure /app is in Python path (fallback if PYTHONPATH env var isn't set)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

from shared.logger import get_logger, bind_job_id
from shared.handlers import sync_handler, sqs_batch_handler
from shared.database import update_job_status_async, update_job_failed_async, get_job_async, JobStatus
from app.processor import download_video

logger = get_logger("url-to-video lambda")


async def process_message(message_body: dict, session) -> bool:
    """Process a single message (async)."""
    job_id = message_body.get("job_id")
    video_url = message_body.get("video_url")

    job_logger = bind_job_id(logger, job_id) if job_id else logger

    if not job_id or not video_url:
        job_logger.warning("Invalid message: missing job_id or video_url")
        return False

    # Idempotency check: skip if video already exists
    job = await get_job_async(session, job_id)
    if job and job.get("video_s3_key"):
        current_status = job.get("status", "")
        job_logger.info(
            "Job already has video, skipping download (S3 event will trigger next stage)",
            video_s3_key=job.get("video_s3_key"),
            status=current_status,
        )
        if current_status == JobStatus.DOWNLOADING.value:
            await update_job_status_async(session, job_id, JobStatus.DOWNLOADED.value, None)
        return True

    try:
        job_logger.info("Processing job: downloading video", video_url=video_url)
        await download_video(video_url, job_id, session)
        job_logger.info("Successfully downloaded and uploaded video")
        return True
    except Exception as e:
        job_logger.error("Error processing job", exc_info=True, error=str(e))
        await update_job_failed_async(session, job_id, True, str(e))
        return False


async_handler = sqs_batch_handler(process_message, logger)
handler = sync_handler(async_handler, logger)
