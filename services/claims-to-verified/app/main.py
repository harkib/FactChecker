"""SQS consumer for Claims to Verified transformation (async)."""
import os
import sys
import signal
import json
import asyncio

# Ensure /app is in Python path (fallback if PYTHONPATH env var isn't set)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

from shared.sqs_client import receive_messages, delete_message
from shared.database import init_db, sessionmaker, update_job_status_async, update_job_verified_claims_async
from app.processor import verify_claims

# Global shutdown event
shutdown_event = asyncio.Event()


def signal_handler(sig, frame):
    """Handle shutdown signal."""
    print("Shutdown signal received, finishing current work...")
    shutdown_event.set()


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def get_openai_api_key():
    """Get OpenAI API key from environment variable (injected by ECS from Secrets Manager)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    return api_key


async def process_message(message_body: dict, session):
    """Process a single message (async)."""
    job_id = message_body.get("job_id")
    claims = message_body.get("claims", [])
    
    if not job_id:
        print(f"Invalid message: missing job_id")
        return False
    
    if not claims:
        print(f"Warning: No claims provided for job {job_id}")
        # Mark as completed with empty results (async)
        await update_job_verified_claims_async(session, job_id, {
            "overall": {
                "verdict": "NOT_FACTUAL",
                "confidence": 0.0,
                "summary": "No claims to verify"
            },
            "claim_results": []
        })
        return True
    
    try:
        print(f"Processing job {job_id}: verifying {len(claims)} claims")
        
        openai_api_key = get_openai_api_key()
        if not openai_api_key:
            raise ValueError("OpenAI API key not found")
        
        verified_claims = await verify_claims(claims, openai_api_key)
        
        print(f"Successfully verified claims for job {job_id}")
        
        # Update job with verified claims and mark as completed (async)
        await update_job_verified_claims_async(session, job_id, verified_claims)
        
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
    
    queue_url = os.getenv("CLAIMS_TO_VERIFIED_QUEUE_URL")
    if not queue_url:
        raise ValueError("CLAIMS_TO_VERIFIED_QUEUE_URL environment variable not set")
    
    max_concurrent = int(os.getenv("MAX_CONCURRENT_MESSAGES", "10"))
    semaphore = asyncio.Semaphore(max_concurrent)
    
    print(f"Starting async Claims-to-Verified worker, listening to queue: {queue_url}")
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
        print("Claims-to-Verified worker shutting down")


if __name__ == "__main__":
    main()
