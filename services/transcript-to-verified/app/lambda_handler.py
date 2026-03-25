"""Lambda handler for Transcript to Verified transformation (async)."""
import sys

# Ensure /app is in Python path (fallback if PYTHONPATH env var isn't set)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

from shared.logger import get_logger, bind_job_id
from shared.env import require_env, get_env
from shared.handlers import sync_handler, sqs_batch_handler
from shared.push_notification import send_push_notification
from shared.database import (
    get_job_async,
    update_job_status_async,
    update_job_failed_async,
    update_job_verified_claims_async,
    JobStatus,
)
from app.processor import extract_and_verify_claims

logger = get_logger("transcript-to-verified lambda")


def setup():
    """Validate required env vars before processing any messages."""
    api_provider = get_env("API_PROVIDER", "gemini").lower()
    if api_provider == "openai":
        api_key = require_env("OPENAI_API_KEY")
    elif api_provider == "gemini":
        api_key = require_env("GEMINI_API_KEY")
    else:
        raise ValueError(f"Unknown API provider: {api_provider}. Must be 'openai' or 'gemini'")
    return {
        "assets_bucket": require_env("ASSETS_BUCKET"),
        "api_provider": api_provider,
        "api_key": api_key,
    }


async def process_message(message_body: dict, session, assets_bucket: str, api_provider: str, api_key: str) -> bool:
    """Process a single message (async)."""
    job_id = message_body.get("job_id")
    transcript_s3_key = message_body.get("transcript_s3_key")
    frames_s3_prefix = message_body.get("frames_s3_prefix")

    job_logger = bind_job_id(logger, job_id) if job_id else logger

    if not job_id or not transcript_s3_key or not frames_s3_prefix:
        job_logger.warning("Invalid message: missing required fields")
        return False

    # Idempotency: skip if job already completed
    job = await get_job_async(session, job_id)
    if job and job.get("status") == JobStatus.COMPLETED.value:
        job_logger.info("Job already completed, skipping reprocessing", job_id=job_id)
        return True

    try:
        job_logger.info(
            "Processing job: extracting and verifying claims from transcript and frames",
            transcript_s3_key=transcript_s3_key,
            frames_s3_prefix=frames_s3_prefix,
            api_provider=api_provider,
        )

        await update_job_status_async(session, job_id, JobStatus.EXTRACTING.value, None)

        result = await extract_and_verify_claims(
            job_id, transcript_s3_key, frames_s3_prefix, assets_bucket, api_key, session, api_provider
        )

        title = result.get("title")
        verifications = result.get("verifications", [])

        job_logger.info(
            "Extracted and verified claims",
            verifications_count=len(verifications),
            title=title
        )

        await update_job_verified_claims_async(session, job_id, result)
        await send_push_notification(job_id, session, logger, title=title or "Gut check ready")

        return True
    except Exception as e:
        job_logger.error("Error processing job", exc_info=True, error=str(e))
        await update_job_failed_async(session, job_id, True, str(e))
        return False


async_handler = sqs_batch_handler(process_message, logger, setup_fn=setup)
handler = sync_handler(async_handler, logger)
