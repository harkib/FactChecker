"""SQS consumer for Claims to Verified transformation."""
import os
import sys
import signal
import json

# Ensure /app is in Python path (fallback if PYTHONPATH env var isn't set)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

from shared.sqs_client import receive_messages, delete_message
from shared.database import update_job_status, update_job_verified_claims, init_db
from app.processor import verify_claims

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
    claims = message_body.get("claims", [])
    
    if not job_id:
        print(f"Invalid message: missing job_id")
        return False
    
    if not claims:
        print(f"Warning: No claims provided for job {job_id}")
        # Mark as completed with empty results
        update_job_verified_claims(job_id, {
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
        
        verified_claims = verify_claims(claims, openai_api_key)
        
        print(f"Successfully verified claims for job {job_id}")
        
        # Update job with verified claims and mark as completed
        update_job_verified_claims(job_id, verified_claims)
        
        return True
    except Exception as e:
        print(f"Error processing job {job_id}: {e}")
        update_job_status(job_id, "failed", str(e))
        return False


def main():
    """Main consumer loop."""
    # Initialize database pool
    init_db()
    
    queue_url = os.getenv("CLAIMS_TO_VERIFIED_QUEUE_URL")
    if not queue_url:
        raise ValueError("CLAIMS_TO_VERIFIED_QUEUE_URL environment variable not set")
    
    print(f"Starting Claims-to-Verified worker, listening to queue: {queue_url}")
    
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
    
    print("Claims-to-Verified worker shutting down")


if __name__ == "__main__":
    main()

