"""Sample worker for testing async DB connections and async task processing."""
import os
import sys
import signal
import asyncio
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Ensure /app is in Python path (fallback if PYTHONPATH env var isn't set)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

from shared.database import init_db, sessionmaker
from app.processor import process_sample_message

# Global shutdown event
shutdown_event = asyncio.Event()

def signal_handler(sig, frame):
    """Handle shutdown signal."""
    print("Shutdown signal received, finishing current work...")
    shutdown_event.set()


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


async def create_dummy_messages(count: int = 20):
    """
    Create multiple dummy messages by creating jobs in the database.
    Returns a list of dicts like [{"job_id": <uuid str>}, ...].
    """
    from shared.database import create_job_async
    messages = []
    async with sessionmaker() as session:
        for i in range(count):
            # Generate a unique video URL
            video_url = f"https://example.com/video_{int(time.time())}_{i}.mp4"
            job_id = await create_job_async(session, video_url)
            messages.append({"job_id": job_id})
    return messages


async def worker_task(semaphore: asyncio.Semaphore, message_body: dict):
    """Process a single message with concurrency control (async)."""
    async with semaphore:  # Limits concurrent processing
        # Each task gets its own session to avoid concurrent access issues
        async with sessionmaker() as session:
            try:
                job_id = message_body.get("job_id")
                if not job_id:
                    print(f"Invalid message: missing job_id")
                    return False
                
                success = await process_sample_message(job_id, session)
                
                if success:
                    print(f"Successfully processed message for job {job_id}")
                else:
                    print(f"Failed to process message for job {job_id}")
                
                return success
            except Exception as e:
                print(f"Error processing message: {e}")
                return False


async def main_async():
    """Main async consumer loop."""
    await init_db()
    
    if sessionmaker is None:
        raise RuntimeError("Database initialization failed: sessionmaker is None")
    
    max_concurrent = 5
    batch_size = max_concurrent  # Process up to max_concurrent messages at a time
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # Create all dummy messages upfront
    print(f"Creating dummy messages...")
    all_messages = await create_dummy_messages(count=20)
    print(f"Created {len(all_messages)} dummy messages")
    
    print(f"Starting sample worker")
    print(f"Max concurrent messages: {max_concurrent}")
    print(f"Processing {batch_size} messages per batch until shutdown...")
    
    # Track which messages we've processed
    message_index = 0
    
    # Main processing loop - runs until shutdown or all messages processed
    while not shutdown_event.is_set() and message_index < len(all_messages):
        try:
            # Get next batch of messages
            batch_messages = []
            for _ in range(batch_size):
                if shutdown_event.is_set() or message_index >= len(all_messages):
                    break
                
                batch_messages.append(all_messages[message_index])
                message_index += 1
            
            if not batch_messages:
                break
            
            print(f"Processing batch of {len(batch_messages)} messages (total processed: {message_index})...")
            
            # Create tasks for the batch - each task will create its own session
            tasks = [
                worker_task(semaphore, msg)
                for msg in batch_messages
            ]
            
            # Process batch concurrently (limited by semaphore)
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Print batch summary
            successful = sum(1 for r in results if r is True)
            failed = len(results) - successful
            print(f"Batch complete: {successful} successful, {failed} failed")
            
            # Small delay before next batch
            await asyncio.sleep(1)
            
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
        print("Sample worker shutting down")


if __name__ == "__main__":
    main()
