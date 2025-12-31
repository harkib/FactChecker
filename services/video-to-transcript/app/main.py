"""SQS consumer for Video to Transcript transformation."""
import os
import json
import sys
import signal

# Ensure /app is in Python path (fallback if PYTHONPATH env var isn't set)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

from shared.sqs_client import receive_messages, delete_message
from shared.database import update_job_status, init_db
from app.processor import process_video

# Global flag for graceful shutdown
shutdown = False


def signal_handler(sig, frame):
    """Handle shutdown signal."""
    global shutdown
    shutdown = True
    print("Shutdown signal received, finishing current work...")


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def process_message(message_body: dict):
    """Process a single message."""
    job_id = message_body.get("job_id")
    video_s3_key = message_body.get("video_s3_key")
    
    if not job_id or not video_s3_key:
        print(f"Invalid message: missing job_id or video_s3_key")
        return False
    
    try:
        print(f"Processing job {job_id}: extracting transcript and frames from {video_s3_key}")
        
        video_bucket = os.getenv("VIDEO_BUCKET")
        assets_bucket = os.getenv("ASSETS_BUCKET")
        
        if not video_bucket or not assets_bucket:
            raise ValueError("VIDEO_BUCKET and ASSETS_BUCKET must be set")
        
        transcript_s3_key, frames_s3_prefix = process_video(
            video_s3_key, job_id, video_bucket, assets_bucket
        )
        
        print(f"Successfully processed video for job {job_id}")
        print(f"  Transcript: {transcript_s3_key}")
        print(f"  Frames: {frames_s3_prefix}")
        
        # Send message to next queue (transcript-to-claims)
        from shared.sqs_client import send_message
        next_queue_url = os.getenv("TRANSCRIPT_TO_CLAIMS_QUEUE_URL")
        if next_queue_url:
            send_message(next_queue_url, {
                "job_id": job_id,
                "transcript_s3_key": transcript_s3_key,
                "frames_s3_prefix": frames_s3_prefix,
            })
            print(f"Sent message to transcript-to-claims queue for job {job_id}")
        else:
            print(f"Warning: TRANSCRIPT_TO_CLAIMS_QUEUE_URL not configured")
        
        return True
    except Exception as e:
        print(f"Error processing job {job_id}: {e}")
        update_job_status(job_id, "failed", str(e))
        return False


def main():
    """Main consumer loop."""
    # Initialize database pool
    init_db()
    
    queue_url = os.getenv("VIDEO_TO_TRANSCRIPT_QUEUE_URL")
    if not queue_url:
        raise ValueError("VIDEO_TO_TRANSCRIPT_QUEUE_URL environment variable not set")
    
    print(f"Starting Video-to-Transcript worker, listening to queue: {queue_url}")
    
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
    
    print("Video-to-Transcript worker shutting down")


if __name__ == "__main__":
    main()

