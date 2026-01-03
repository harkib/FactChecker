"""FastAPI REST API service for fact-checking jobs."""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import sys

# Add shared directory to path
# From /app/app/main.py, go up one level to /app, then shared is at /app/shared
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CreateJobRequest, CreateJobResponse, JobResponse
from app.services import create_fact_check_job, get_job_by_id
from shared.database import init_db, get_db
from shared.logger import get_logger, bind_job_id

# Initialize logger with resource name
logger = get_logger("api")

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


@app.post("/jobs", response_model=CreateJobResponse, status_code=201)
async def create_job(request: CreateJobRequest, db: AsyncSession = Depends(get_db)):
    """Create a new fact-checking job."""
    try:
        logger.info("Creating new fact-checking job", video_url=str(request.video_url))
        job_id = await create_fact_check_job(db, str(request.video_url))
        job_logger = bind_job_id(logger, job_id)
        job_logger.info("Job created successfully", status="pending")
        return CreateJobResponse(job_id=job_id, status="pending")
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
    if job["status"] != "completed":
        job_logger.warning("Job not completed", current_status=job["status"])
        raise HTTPException(status_code=400, detail=f"Job is not completed. Current status: {job['status']}")
    job_logger.info("Job results retrieved successfully")
    return JobResponse(**job)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    logger.debug("Health check requested")
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

