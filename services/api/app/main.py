"""FastAPI REST API service for fact-checking jobs."""
from base64 import decode
from codecs import utf_16_be_decode
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import os
import sys
import re
import time

# Add shared directory to path
# From /app/app/main.py, go up one level to /app, then shared is at /app/shared
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from app.models import CreateJobRequest, CreateJobResponse, JobResponse, CreateUploadJobResponse, GetUploadUrlResponse, RegisterDeviceTokenRequest
from app.auth_models import AppleSignInRequest, AppleSignInResponse
from app.services import create_fact_check_job, get_job_by_id, get_jobs_by_client_id, generate_presigned_frame_url, create_upload_job, generate_presigned_upload_url, register_device_token
from app.auth import verify_apple_identity_token, create_api_gateway_api_key
from app.migrations import run_migrations
from shared.database import get_db, JobStatus, Job
import uuid
from shared.logger import get_logger, bind_job_id, configure_logging

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


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Log HTTP exceptions (400, 404, 403, 500, etc.) with request context."""
    # Determine log level based on status code
    status_code = exc.status_code
    if 400 <= status_code < 500:
        # Client errors (4xx) - log as warning
        log_level = "warning"
    else:
        # Server errors (5xx) - log as error
        log_level = "error"
    
    # Extract client ID from headers if available
    client_id = request.headers.get("X-Client-ID")
    
    # Log the error with context
    log_data = {
        "path": request.url.path,
        "method": request.method,
        "status_code": status_code,
        "detail": exc.detail,
        "client_id": client_id,
    }
    
    if log_level == "warning":
        logger.warning("HTTP error", **log_data)
    else:
        logger.error("HTTP error", **log_data)
    
    # Return the standard FastAPI error response
    return JSONResponse(
        status_code=status_code,
        content={"detail": exc.detail}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log request validation errors (Pydantic validation failures) with validation details."""
    # Extract client ID from headers if available
    client_id = request.headers.get("X-Client-ID")
    
    # Format validation errors for logging
    errors = exc.errors()
    error_details = []
    for error in errors:
        error_details.append({
            "field": ".".join(str(loc) for loc in error.get("loc", [])),
            "message": error.get("msg"),
            "type": error.get("type"),
        })
    
    # Log the validation error
    log_data = {
        "path": request.url.path,
        "method": request.method,
        "status_code": 422,
        "validation_errors": error_details,
        "client_id": client_id,
    }
    
    logger.warning("Request validation error", **log_data)
    
    # Return the standard FastAPI validation error response
    return JSONResponse(
        status_code=422,
        content={"detail": errors}
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Log all unhandled exceptions (including SQLAlchemy/database errors) with full context."""
    # Extract client ID from headers if available
    client_id = request.headers.get("X-Client-ID")
    
    # Build log data with request context
    log_data = {
        "path": request.url.path,
        "method": request.method,
        "status_code": 500,
        "exception_type": type(exc).__name__,
        "exception_message": str(exc),
        "client_id": client_id,
    }
    
    # Log the unhandled exception with full traceback
    logger.error("Unhandled exception", exc_info=True, **log_data)
    
    # Return 500 error response
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests for better observability."""
    start_time = time.time()
    
    # Extract client ID from headers if available
    client_id = request.headers.get("X-Client-ID")
    
    # Log request
    log_data = {
        "path": request.url.path,
        "method": request.method,
        "client_id": client_id,
    }
    logger.debug("Incoming request", **log_data)
    
    # Process request
    response = await call_next(request)
    
    # Calculate duration
    duration = time.time() - start_time
    
    # Log response
    response_log_data = {
        "path": request.url.path,
        "method": request.method,
        "status_code": response.status_code,
        "duration_ms": round(duration * 1000, 2),
        "client_id": client_id,
    }
    
    # Use appropriate log level based on status code
    if response.status_code >= 500:
        logger.error("Request completed", **response_log_data)
    elif response.status_code >= 400:
        logger.warning("Request completed", **response_log_data)
    else:
        logger.debug("Request completed", **response_log_data)
    
    return response


@app.on_event("startup")
async def startup_event():
    """Initialize database connection pool and run migrations on startup."""
    logger.info("Starting API service")
    await run_migrations()
    configure_logging()
    logger.info("Database migrations completed and connection pool initialized")


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

@app.post("/upload-jobs", response_model=CreateUploadJobResponse, status_code=201)
async def create_upload_job_endpoint(
    db: AsyncSession = Depends(get_db),
    client_id: Optional[str] = Depends(get_client_id)
):
    """Create a new job for direct video upload and return S3 presigned upload URL."""
    try:
        # Client ID is required
        if not client_id:
            logger.warning("Missing client ID in request")
            raise HTTPException(status_code=400, detail="X-Client-ID header is required")
        
        logger.info("Creating new upload job", client_id=client_id)
        
        # Create job and get S3 key
        job_id, video_s3_key = await create_upload_job(db, client_id)
        job_logger = bind_job_id(logger, job_id)
        job_logger.debug("Upload job created", video_s3_key=video_s3_key)
        
        # Get video bucket name from environment
        video_bucket = os.getenv("VIDEO_BUCKET")
        if not video_bucket:
            job_logger.error("VIDEO_BUCKET not configured")
            raise HTTPException(status_code=500, detail="VIDEO_BUCKET not configured")
        
        # Generate presigned upload URL (1 hour expiration)
        upload_url = await generate_presigned_upload_url(video_bucket, video_s3_key, expiration=3600)
        
        if not upload_url:
            job_logger.error("Failed to generate presigned upload URL")
            raise HTTPException(status_code=500, detail="Failed to generate presigned upload URL")
        
        job_logger.info("Upload URL generated successfully")
        return CreateUploadJobResponse(
            job_id=job_id,
            upload_url=upload_url,
            expires_in=3600
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create upload job", exc_info=True, error=str(e), client_id=client_id)
        raise HTTPException(status_code=500, detail=f"Failed to create upload job: {str(e)}")


@app.post("/device-token", status_code=204)
async def register_device_token_endpoint(
    request: RegisterDeviceTokenRequest,
    db: AsyncSession = Depends(get_db),
    client_id: Optional[str] = Depends(get_client_id),
):
    """Register device token for push notifications. Requires X-Client-ID header."""
    try:
        if not client_id:
            raise HTTPException(status_code=400, detail="X-Client-ID header is required")
        if not request.device_token or not request.device_token.strip():
            raise HTTPException(status_code=400, detail="device_token is required")
        await register_device_token(
            db, client_id, request.device_token.strip(), sandbox=request.sandbox
        )
        return None
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Device token registration failed", error=str(e), client_id=client_id)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to register device token", exc_info=True, error=str(e), client_id=client_id)
        raise HTTPException(status_code=500, detail="Failed to register device token")


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


@app.get("/jobs/{job_id}/upload-url", response_model=GetUploadUrlResponse)
async def get_upload_url(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    client_id: Optional[str] = Depends(get_client_id)
):
    """Get S3 presigned upload URL for a failed job (hybrid upload recovery)."""
    job_logger = bind_job_id(logger, job_id)
    job_logger.debug("Getting upload URL for job")
    
    try:
        # Get job from database
        job = await get_job_by_id(db, job_id)
        if not job:
            job_logger.warning("Job not found")
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Validate that the job belongs to the requesting client
        if client_id and job.get("client_id") != client_id:
            job_logger.warning("Job does not belong to client", client_id=client_id, job_client_id=job.get("client_id"))
            raise HTTPException(status_code=403, detail="Job does not belong to this client")
        
        # Validate job status and failed flag
        job_status = job.get("status")
        job_failed = job.get("failed", False)
        
        if job_status != JobStatus.DOWNLOADING.value or not job_failed:
            job_logger.warning(
                "Job not eligible for upload recovery",
                status=job_status,
                failed=job_failed
            )
            raise HTTPException(
                status_code=400,
                detail=f"Job is not eligible for upload recovery. Status must be 'downloading' and failed must be true. Current: status={job_status}, failed={job_failed}"
            )
        
        # Get or generate S3 key
        video_s3_key = job.get("video_s3_key")
        if not video_s3_key:
            video_s3_key = f"videos/{job_id}.mp4"
            # Update job with S3 key
            from sqlalchemy import select
            stmt = select(Job).where(Job.id == uuid.UUID(job_id))
            result = await db.execute(stmt)
            job_obj = result.scalar_one_or_none()
            if job_obj:
                job_obj.video_s3_key = video_s3_key
                await db.commit()
        
        # Get video bucket name from environment
        video_bucket = os.getenv("VIDEO_BUCKET")
        if not video_bucket:
            job_logger.error("VIDEO_BUCKET not configured")
            raise HTTPException(status_code=500, detail="VIDEO_BUCKET not configured")
        
        # Generate presigned upload URL (1 hour expiration)
        upload_url = await generate_presigned_upload_url(video_bucket, video_s3_key, expiration=3600)
        
        if not upload_url:
            job_logger.error("Failed to generate presigned upload URL")
            raise HTTPException(status_code=500, detail="Failed to generate presigned upload URL")
        
        job_logger.info("Upload URL generated successfully for failed job")
        return GetUploadUrlResponse(
            upload_url=upload_url,
            expires_in=3600
        )
        
    except HTTPException:
        raise
    except Exception as e:
        job_logger.error("Failed to get upload URL", exc_info=True, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get upload URL: {str(e)}")


@app.post("/auth/apple-signin", response_model=AppleSignInResponse, status_code=200)
async def apple_sign_in(request: AppleSignInRequest):
    """Apple Sign In endpoint - verifies Apple token and returns API Gateway API key.
    
    This endpoint does not require authentication (no API key needed).
    """
    try:
        logger.info("Apple Sign In request received")
        
        # Verify Apple identity token
        token_claims = await verify_apple_identity_token(request.identity_token)
        if not token_claims:
            logger.warning("Apple identity token verification failed")
            raise HTTPException(status_code=401, detail="Invalid Apple identity token")
        
        # Extract user identifier from token
        user_id = token_claims.get("sub")
        if not user_id:
            logger.warning("Token missing user identifier")
            raise HTTPException(status_code=401, detail="Token missing user identifier")
        
        logger.debug("Apple identity token verified", user_id=user_id)
        
        # Get API Gateway configuration from environment
        api_gateway_rest_api_id = os.getenv("API_GATEWAY_REST_API_ID")
        usage_plan_id = os.getenv("API_GATEWAY_USAGE_PLAN_ID")
        
        if not api_gateway_rest_api_id or not usage_plan_id:
            logger.error("API Gateway configuration missing", 
                        has_rest_api_id=bool(api_gateway_rest_api_id),
                        has_usage_plan_id=bool(usage_plan_id))
            raise HTTPException(status_code=500, detail="API Gateway configuration missing")
        
        # Create API Gateway API key
        api_key_value = await create_api_gateway_api_key(
            api_gateway_rest_api_id=api_gateway_rest_api_id,
            usage_plan_id=usage_plan_id,
            description=f"API key for Apple user {user_id}"
        )
        
        if not api_key_value:
            logger.error("Failed to create API Gateway API key")
            raise HTTPException(status_code=500, detail="Failed to create API key")
        
        logger.info("API key created successfully for Apple Sign In", user_id=user_id)
        return AppleSignInResponse(auth_key=api_key_value)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing Apple Sign In", exc_info=True, error=str(e))
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    logger.debug("Health check requested")
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

