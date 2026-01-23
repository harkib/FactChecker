"""FastAPI REST API service for fact-checking jobs."""
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
import os
import sys
import re

# Add shared directory to path
# From /app/app/main.py, go up one level to /app, then shared is at /app/shared
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from app.models import CreateJobRequest, CreateJobResponse, JobResponse
from app.services import create_fact_check_job, get_job_by_id, get_jobs_by_client_id, generate_presigned_frame_url
from shared.database import init_db, get_db, JobStatus
from shared.logger import get_logger, bind_job_id

# Initialize logger with resource name
logger = get_logger("api")

# UUID validation regex (matches standard UUID format)
UUID_REGEX = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)


def validate_client_id(client_id: Optional[str]) -> Optional[str]:
    """Validate client ID format (should be UUID format).
    
    Args:
        client_id: Client ID string to validate
        
    Returns:
        Validated client ID or None if invalid/empty
    """
    if not client_id:
        return None
    
    # Strip whitespace
    client_id = client_id.strip()
    
    # Check if it matches UUID format
    if UUID_REGEX.match(client_id):
        return client_id
    
    # If it doesn't match, log warning but don't reject (for backwards compatibility)
    logger.warning("Client ID does not match UUID format", client_id=client_id)
    return client_id


async def get_client_id(x_client_id: Optional[str] = Header(None, alias="X-Client-ID")) -> Optional[str]:
    """FastAPI dependency to extract and validate client ID from header.
    
    Args:
        x_client_id: Client ID from X-Client-ID header
        
    Returns:
        Validated client ID or None
    """
    return validate_client_id(x_client_id)

app = FastAPI(title="FactChecker API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize database connection pool on startup."""
    logger.info("Starting API service")
    await init_db()
    logger.info("Database connection pool initialized")


@app.get("/jobs", response_model=List[JobResponse])
async def get_jobs(
    db: AsyncSession = Depends(get_db),
    client_id: Optional[str] = Depends(get_client_id)
):
    """Get last 10 jobs for a client_id, ordered by creation date (most recent first)."""
    try:
        # Client ID is required
        if not client_id:
            logger.warning("Missing client ID in request")
            raise HTTPException(status_code=400, detail="X-Client-ID header is required")
        
        logger.debug("Getting jobs for client", client_id=client_id)
        jobs = await get_jobs_by_client_id(db, client_id)
        logger.debug("Jobs retrieved successfully", count=len(jobs), client_id=client_id)
        return [JobResponse(**job) for job in jobs]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get jobs", exc_info=True, error=str(e), client_id=client_id)
        raise HTTPException(status_code=500, detail=f"Failed to get jobs: {str(e)}")


@app.post("/jobs", response_model=CreateJobResponse, status_code=201)
async def create_job(
    request: CreateJobRequest,
    db: AsyncSession = Depends(get_db),
    client_id: Optional[str] = Depends(get_client_id)
):
    """Create a new fact-checking job."""
    try:
        # Client ID is required
        if not client_id:
            logger.warning("Missing client ID in request")
            raise HTTPException(status_code=400, detail="X-Client-ID header is required")
        
        logger.info(
            "Creating new fact-checking job",
            video_url=str(request.video_url),
            client_id=client_id
        )
        job_id = await create_fact_check_job(db, str(request.video_url), client_id=client_id)
        job_logger = bind_job_id(logger, job_id)
        job_logger.info("Job created successfully", status=JobStatus.PENDING.value, client_id=client_id)
        return CreateJobResponse(job_id=job_id, status=JobStatus.PENDING.value)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create job", exc_info=True, error=str(e), video_url=str(request.video_url))
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Get job status and results."""
    job_logger = bind_job_id(logger, job_id)
    job_logger.debug("Getting job status and results")
    job = await get_job_by_id(db, job_id)
    if not job:
        job_logger.warning("Job not found")
        raise HTTPException(status_code=404, detail="Job not found")
    job_logger.debug("Job retrieved successfully", status=job.get("status"))
    return JobResponse(**job)


@app.get("/jobs/{job_id}/results", response_model=JobResponse)
async def get_job_results(job_id: str, db: AsyncSession = Depends(get_db)):
    """Get verified claims for a completed job."""
    job_logger = bind_job_id(logger, job_id)
    job_logger.debug("Getting job results")
    job = await get_job_by_id(db, job_id)
    if not job:
        job_logger.warning("Job not found")
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != JobStatus.COMPLETED.value:
        job_logger.warning("Job not completed", current_status=job["status"])
        raise HTTPException(status_code=400, detail=f"Job is not completed. Current status: {job['status']}")
    job_logger.info("Job results retrieved successfully")
    return JobResponse(**job)


@app.get("/jobs/{job_id}/thumbnail-url")
async def get_thumbnail_url(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    client_id: Optional[str] = Depends(get_client_id)
):
    """Get presigned URL for the first frame thumbnail of a job."""
    job_logger = bind_job_id(logger, job_id)
    job_logger.debug("Getting thumbnail URL")
    
    try:
        # Get job from database
        job = await get_job_by_id(db, job_id)
        if not job:
            job_logger.warning("Job not found")
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Optional: Validate that the job belongs to the requesting client
        if client_id and job.get("client_id") != client_id:
            job_logger.warning("Job does not belong to client", client_id=client_id, job_client_id=job.get("client_id"))
            raise HTTPException(status_code=403, detail="Job does not belong to this client")
        
        # Check if job has frames
        frames_s3_prefix = job.get("frames_s3_prefix")
        if not frames_s3_prefix:
            job_logger.debug("Job has no frames")
            raise HTTPException(status_code=404, detail="Job has no frames")
        
        # Construct the first frame key (first frame is always 0.00.jpg)
        # Ensure prefix ends with / if it doesn't already
        prefix = frames_s3_prefix if frames_s3_prefix.endswith("/") else f"{frames_s3_prefix}/"
        frame_key = f"{prefix}0.00.jpg"
        
        # Get assets bucket name from environment
        assets_bucket = os.getenv("ASSETS_BUCKET")
        if not assets_bucket:
            job_logger.error("ASSETS_BUCKET not configured")
            raise HTTPException(status_code=500, detail="ASSETS_BUCKET not configured")
        
        # Generate presigned URL (1 hour expiration)
        presigned_url = await generate_presigned_frame_url(assets_bucket, frame_key, expiration=3600)
        
        if not presigned_url:
            job_logger.error("Failed to generate presigned URL")
            raise HTTPException(status_code=500, detail="Failed to generate presigned URL")
        
        job_logger.debug("Thumbnail URL generated successfully")
        return {"url": presigned_url}
        
    except HTTPException:
        raise
    except Exception as e:
        job_logger.error("Failed to get thumbnail URL", exc_info=True, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get thumbnail URL: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    logger.debug("Health check requested")
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

