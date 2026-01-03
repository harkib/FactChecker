"""SQS consumer for URL to Video transformation (async)."""
import os
import json
import sys
import signal
import asyncio

# Ensure /app is in Python path (fallback if PYTHONPATH env var isn't set)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

from shared.sqs_client import receive_messages, delete_message, send_message
from shared.database import init_db, sessionmaker, update_job_status_async
from shared.logger import get_logger, bind_job_id
from app.processor import download_video

# Initialize logger with resource name
logger = get_logger("url-to-video worker")

# Global shutdown event
shutdown_event = asyncio.Event()


def signal_handler(sig, frame):
    """Handle shutdown signal."""
    logger.info("Shutdown signal received, finishing current work...")
    shutdown_event.set()


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


async def process_message(message_body: dict, session):
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
        next_queue_url = os.getenv("VIDEO_TO_TRANSCRIPT_QUEUE_URL")
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
        await update_job_status_async(session, job_id, "failed", str(e))
        return False


async def worker_task(semaphore: asyncio.Semaphore, message, queue_url):
    """Process a single message with concurrency control (async)."""
    async with semaphore:  # Limits concurrent processing
        # Each task gets its own session to avoid concurrent access issues
        async with sessionmaker() as session:
            try:
                message_body = json.loads(message["Body"])
                receipt_handle = message["ReceiptHandle"]
                job_id = message_body.get("job_id")
                job_logger = bind_job_id(logger, job_id) if job_id else logger
                
                success = await process_message(message_body, session)
                
                if success:
                    await delete_message(queue_url, receipt_handle)
                    job_logger.info("Processed and deleted message")
                else:
                    job_logger.warning("Failed to process message, will retry")
            except json.JSONDecodeError as e:
                logger.error("Error decoding message", exc_info=True, error=str(e))
                await delete_message(queue_url, message["ReceiptHandle"])
            except Exception as e:
                logger.error("Error processing message", exc_info=True, error=str(e))


async def main_async():
    """Main async consumer loop."""
    await init_db()
    
    # Verify database initialization completed
    if sessionmaker is None:
        raise RuntimeError("Database initialization failed: sessionmaker is None")
    
    queue_url = os.getenv("URL_TO_VIDEO_QUEUE_URL")
    if not queue_url:
        raise ValueError("URL_TO_VIDEO_QUEUE_URL environment variable not set")
    
    max_concurrent = int(os.getenv("MAX_CONCURRENT_MESSAGES", "10"))
    semaphore = asyncio.Semaphore(max_concurrent)
    
    logger.info("Starting async URL-to-Video worker", queue_url=queue_url, max_concurrent=max_concurrent)
    
    while not shutdown_event.is_set():
        try:
            # Receive multiple messages at once (up to 10 from SQS)
            messages = await receive_messages(queue_url, max_messages=min(10, max_concurrent), wait_time_seconds=20)
            
            if not messages:
                continue
            
            # Create tasks for all received messages - each task will create its own session
            tasks = [
                worker_task(semaphore, msg, queue_url)
                for msg in messages
            ]
            
            # Process all messages concurrently (limited by semaphore)
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error("Error in main loop", exc_info=True, error=str(e))
            await asyncio.sleep(5)


def main():
    """Entry point with signal handling."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("URL-to-Video worker shutting down")


if __name__ == "__main__":
    main()
