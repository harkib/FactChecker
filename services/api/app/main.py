"""FastAPI REST API service for fact-checking jobs."""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import sys

# Add shared directory to path
# From /app/app/main.py, go up one level to /app, then shared is at /app/shared
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from app.models import CreateJobRequest, CreateJobResponse, JobResponse
from app.services import create_fact_check_job, get_job_by_id
from shared.database import init_db

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
    init_db()


@app.post("/jobs", response_model=CreateJobResponse, status_code=201)
async def create_job(request: CreateJobRequest):
    """Create a new fact-checking job."""
    try:
        job_id = create_fact_check_job(str(request.video_url))
        return CreateJobResponse(job_id=job_id, status="pending")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """Get job status and results."""
    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**job)


@app.get("/jobs/{job_id}/results", response_model=JobResponse)
async def get_job_results(job_id: str):
    """Get verified claims for a completed job."""
    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Job is not completed. Current status: {job['status']}")
    return JobResponse(**job)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

