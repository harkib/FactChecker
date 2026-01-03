"""Sample message processor (async) - simple wait and print for testing."""
import asyncio
import random
from sqlalchemy.ext.asyncio import AsyncSession
from shared.database import update_job_status_async
from shared.logger import get_logger, bind_job_id

# Initialize logger with resource name
logger = get_logger("sample-worker")


async def process_sample_message(job_id: str, session: AsyncSession) -> bool:
    """
    Process a sample message by waiting randomly and printing status (async).
    
    Args:
        job_id: Job ID to process
        session: Async database session
    
    Returns:
        True if successful, False otherwise
    """
    # Bind job_id to logger context
    job_logger = bind_job_id(logger, job_id)
    
    try:
        job_logger.info("Starting processing")
        
        # Update job status to processing
        await update_job_status_async(session, job_id, "processing", None)
        job_logger.debug("Status updated to 'processing'")
        
        # Random wait between 1-5 seconds
        wait_time = random.uniform(1.0, 5.0)
        job_logger.debug("Waiting before completion", wait_time_seconds=round(wait_time, 2))
        await asyncio.sleep(wait_time)
        
        # Update job status to completed
        await update_job_status_async(session, job_id, "completed", None)
        job_logger.info("Processing complete")
        
        return True
    except Exception as e:
        job_logger.error("Error during processing", exc_info=True, error=str(e))
        try:
            await update_job_status_async(session, job_id, "failed", str(e))
        except Exception as db_error:
            job_logger.error("Failed to update DB status", exc_info=True, error=str(db_error))
        return False
