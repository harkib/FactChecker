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
from app.processor import download_video

# Global shutdown event
shutdown_event = asyncio.Event()


def signal_handler(sig, frame):
    """Handle shutdown signal."""
    print("Shutdown signal received, finishing current work...")
    shutdown_event.set()


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


async def process_message(message_body: dict, session):
    """Process a single message (async)."""
    job_id = message_body.get("job_id")
    video_url = message_body.get("video_url")
    
    if not job_id or not video_url:
        print(f"Invalid message: missing job_id or video_url")
        return False
    
    try:
        print(f"Processing job {job_id}: downloading video from {video_url}")
        s3_key = await download_video(video_url, job_id, session)
        print(f"Successfully downloaded and uploaded video for job {job_id} to {s3_key}")
        
        # Send message to next queue (video-to-transcript)
        next_queue_url = os.getenv("VIDEO_TO_TRANSCRIPT_QUEUE_URL")
        if next_queue_url:
            await send_message(next_queue_url, {
                "job_id": job_id,
                "video_s3_key": s3_key,
            })
            print(f"Sent message to video-to-transcript queue for job {job_id}")
        else:
            print(f"Warning: VIDEO_TO_TRANSCRIPT_QUEUE_URL not configured")
        
        return True
    except Exception as e:
        print(f"Error processing job {job_id}: {e}")
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
                
                success = await process_message(message_body, session)
                
                if success:
                    await delete_message(queue_url, receipt_handle)
                    print(f"Processed and deleted message for job {message_body.get('job_id')}")
                else:
                    print(f"Failed to process message, will retry")
            except json.JSONDecodeError as e:
                print(f"Error decoding message: {e}")
                await delete_message(queue_url, message["ReceiptHandle"])
            except Exception as e:
                print(f"Error processing message: {e}")


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
    
    print(f"Starting async URL-to-Video worker, listening to queue: {queue_url}")
    print(f"Max concurrent messages: {max_concurrent}")
    
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
            print(f"Error in main loop: {e}")
            await asyncio.sleep(5)


def main():
    """Entry point with signal handling."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass
    finally:
        print("URL-to-Video worker shutting down")


if __name__ == "__main__":
    main()
