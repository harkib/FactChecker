"""Sample message processor (async) - simple wait and print for testing."""
import asyncio
import random
from sqlalchemy.ext.asyncio import AsyncSession
from shared.database import update_job_status_async


async def process_sample_message(job_id: str, session: AsyncSession) -> bool:
    """
    Process a sample message by waiting randomly and printing status (async).
    
    Args:
        job_id: Job ID to process
        session: Async database session
    
    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"[{job_id}] Starting processing...")
        
        # Update job status to processing
        await update_job_status_async(session, job_id, "processing", None)
        print(f"[{job_id}] Status updated to 'processing'")
        
        # Random wait between 1-5 seconds
        wait_time = random.uniform(1.0, 5.0)
        print(f"[{job_id}] Waiting for {wait_time:.2f} seconds...")
        await asyncio.sleep(wait_time)
        
        # Update job status to completed
        await update_job_status_async(session, job_id, "completed", None)
        print(f"[{job_id}] Processing complete!")
        
        return True
    except Exception as e:
        print(f"[{job_id}] Error during processing: {e}")
        try:
            await update_job_status_async(session, job_id, "failed", str(e))
        except Exception as db_error:
            print(f"[{job_id}] Failed to update DB status: {db_error}")
        return False
