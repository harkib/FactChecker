"""SQS consumer for Transcript to Claims transformation."""
import os
import sys
import signal
import json

# Ensure /app is in Python path (fallback if PYTHONPATH env var isn't set)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

from shared.sqs_client import receive_messages, delete_message
from shared.database import update_job_status, update_job_claims, init_db
from app.processor import extract_claims

# Global flag for graceful shutdown
shutdown = False


def signal_handler(sig, frame):
    """Handle shutdown signal."""
    global shutdown
    shutdown = True
    print("Shutdown signal received, finishing current work...")


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def get_openai_api_key():
    """Get OpenAI API key from environment variable (injected by ECS from Secrets Manager)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    return api_key


def process_message(message_body: dict):
    """Process a single message."""
    job_id = message_body.get("job_id")
    transcript_s3_key = message_body.get("transcript_s3_key")
    frames_s3_prefix = message_body.get("frames_s3_prefix")
    
    if not job_id or not transcript_s3_key or not frames_s3_prefix:
        print(f"Invalid message: missing required fields")
        return False
    
    try:
        print(f"Processing job {job_id}: extracting claims from transcript and frames")
        
        assets_bucket = os.getenv("ASSETS_BUCKET")
        if not assets_bucket:
            raise ValueError("ASSETS_BUCKET must be set")
        
        openai_api_key = get_openai_api_key()
        if not openai_api_key:
            raise ValueError("OpenAI API key not found")
        
        claims = extract_claims(
            job_id, transcript_s3_key, frames_s3_prefix, assets_bucket, openai_api_key
        )
        
        print(f"Extracted {len(claims)} claims for job {job_id}")
        
        # Update job with claims
        update_job_claims(job_id, claims)
        
        # Send message to next queue (claims-to-verified)
        from shared.sqs_client import send_message
        next_queue_url = os.getenv("CLAIMS_TO_VERIFIED_QUEUE_URL")
        if next_queue_url:
            send_message(next_queue_url, {
                "job_id": job_id,
                "claims": claims,
            })
            print(f"Sent message to claims-to-verified queue for job {job_id}")
        else:
            print(f"Warning: CLAIMS_TO_VERIFIED_QUEUE_URL not configured")
        
        return True
    except Exception as e:
        print(f"Error processing job {job_id}: {e}")
        update_job_status(job_id, "failed", str(e))
        return False


def main():
    """Main consumer loop."""
    # Initialize database pool
    init_db()
    
    queue_url = os.getenv("TRANSCRIPT_TO_CLAIMS_QUEUE_URL")
    if not queue_url:
        raise ValueError("TRANSCRIPT_TO_CLAIMS_QUEUE_URL environment variable not set")
    
    print(f"Starting Transcript-to-Claims worker, listening to queue: {queue_url}")
    
    while not shutdown:
        try:
            messages = receive_messages(queue_url, max_messages=1, wait_time_seconds=20)
            
            for message in messages:
                if shutdown:
                    break
                
                try:
                    message_body = json.loads(message["Body"])
                    receipt_handle = message["ReceiptHandle"]
                    
                    if process_message(message_body):
                        delete_message(queue_url, receipt_handle)
                        print(f"Processed and deleted message for job {message_body.get('job_id')}")
                    else:
                        print(f"Failed to process message, will retry")
                except json.JSONDecodeError as e:
                    print(f"Error decoding message: {e}")
                    # Delete malformed message
                    delete_message(queue_url, message["ReceiptHandle"])
                except Exception as e:
                    print(f"Error processing message: {e}")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            import time
            time.sleep(5)  # Wait before retrying
    
    print("Transcript-to-Claims worker shutting down")


if __name__ == "__main__":
    main()

