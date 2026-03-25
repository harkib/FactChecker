"""Lambda handler for S3 video upload events (async)."""
import sys
import re

# Ensure /app is in Python path (fallback if PYTHONPATH env var isn't set)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

from shared.logger import get_logger, bind_job_id
from shared.env import require_env
from shared.secrets import initialize_secrets
from shared.handlers import sync_handler
from shared.sqs_client import send_message
from shared.database import get_sessionmaker, update_job_video_s3_key_async, JobStatus

logger = get_logger("s3-video-event lambda")


def extract_job_id_from_s3_key(s3_key: str) -> str:
    """Extract job_id from S3 key. Expected format: videos/{job_id}.mp4"""
    match = re.match(r'videos/([^/]+)\.mp4$', s3_key)
    if match:
        return match.group(1)
    raise ValueError(f"Unable to extract job_id from S3 key: {s3_key}")


async def process_s3_event(record, video_to_transcript_queue_url: str) -> bool:
    """Process a single S3 event record (async)."""
    try:
        s3_info = record.get("s3", {})
        bucket_name = s3_info.get("bucket", {}).get("name")
        s3_key = s3_info.get("object", {}).get("key")

        if s3_key:
            import urllib.parse
            s3_key = urllib.parse.unquote_plus(s3_key)

        if not s3_key:
            logger.warning("S3 event missing object key", record=record)
            return False

        logger.info("Processing S3 video upload event", bucket=bucket_name, key=s3_key)

        try:
            job_id = extract_job_id_from_s3_key(s3_key)
        except ValueError as e:
            logger.warning("Failed to extract job_id from S3 key", s3_key=s3_key, error=str(e))
            return False

        job_logger = bind_job_id(logger, job_id)
        job_logger.info("Extracted job_id from S3 key", s3_key=s3_key)

        async with get_sessionmaker()() as session:
            await update_job_video_s3_key_async(session, job_id, s3_key)
            job_logger.info("Updated job with video S3 key", status=JobStatus.DOWNLOADED.value)

        await send_message(video_to_transcript_queue_url, {
            "job_id": job_id,
            "video_s3_key": s3_key,
        })
        job_logger.info("Sent message to video-to-transcript queue")

        return True

    except Exception as e:
        logger.error("Error processing S3 event", exc_info=True, error=str(e), record=record)
        return False


async def async_handler(event, context):
    """Async Lambda handler for S3 event notifications."""
    await initialize_secrets()

    video_to_transcript_queue_url = require_env("VIDEO_TO_TRANSCRIPT_QUEUE_URL")

    success_count = 0
    failure_count = 0

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


handler = sync_handler(async_handler, logger)
