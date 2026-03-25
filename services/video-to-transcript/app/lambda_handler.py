"""Lambda handler for Video to Transcript transformation (async)."""
import sys

# Ensure /app is in Python path (fallback if PYTHONPATH env var isn't set)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

from shared.logger import get_logger, bind_job_id
from shared.env import require_env
from shared.handlers import sync_handler, sqs_batch_handler
from shared.sqs_client import send_message
from shared.database import get_sessionmaker, get_job_async, update_job_status_async, update_job_failed_async, JobStatus
from app.processor import process_video

logger = get_logger("video-to-transcript lambda")


def setup():
    """Validate required env vars before processing any messages."""
    return {
        "next_queue_url": require_env("TRANSCRIPT_TO_CLAIMS_QUEUE_URL"),
        "video_bucket": require_env("VIDEO_BUCKET"),
        "assets_bucket": require_env("ASSETS_BUCKET"),
    }


async def process_message(message_body: dict, session, next_queue_url: str, video_bucket: str, assets_bucket: str) -> bool:
    """Process a single message (async)."""
    job_id = message_body.get("job_id")
    video_s3_key = message_body.get("video_s3_key")

    job_logger = bind_job_id(logger, job_id) if job_id else logger

    if not job_id or not video_s3_key:
        job_logger.warning("Invalid message: missing job_id or video_s3_key")
        return False

    # Idempotency: skip if job already has transcript
    job = await get_job_async(session, job_id)
    if job and job.get("transcript_s3_key") and job.get("frames_s3_prefix"):
        job_logger.info(
            "Job already has transcript and frames, skipping reprocessing",
            job_id=job_id,
        )
        return True

    try:
        job_logger.info("Processing job: extracting transcript and frames", video_s3_key=video_s3_key)

        transcript_s3_key, frames_s3_prefix = await process_video(
            video_s3_key, job_id, video_bucket, assets_bucket, session
        )

        job_logger.info(
            "Successfully processed video",
            transcript_s3_key=transcript_s3_key,
            frames_s3_prefix=frames_s3_prefix
        )

        await send_message(next_queue_url, {
            "job_id": job_id,
            "transcript_s3_key": transcript_s3_key,
            "frames_s3_prefix": frames_s3_prefix,
        })
        job_logger.info("Sent message to transcript-to-claims queue")

        return True
    except Exception as e:
        job_logger.error("Error processing job", exc_info=True, error=str(e))
        await update_job_failed_async(session, job_id, True, str(e))
        return False


async_handler = sqs_batch_handler(process_message, logger, setup_fn=setup)
handler = sync_handler(async_handler, logger)
