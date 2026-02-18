"""Database models and utilities for job tracking using SQLAlchemy async."""
import os
from enum import Enum
from typing import Optional, Dict, Any, AsyncGenerator, List
from sqlalchemy import Column, String, Text, DateTime, Boolean, select, desc
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class JobStatus(str, Enum):
    """Job status enumeration."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    PROCESSING = "processing"  # transcript extraction in progress
    TRANSCRIBED = "transcribed"
    EXTRACTING = "extracting"  # claims extraction in progress
    CLAIMS_EXTRACTED = "claims_extracted"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base):
    """SQLAlchemy model for jobs table."""
    __tablename__ = "jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_url = Column(Text, nullable=False)
    status = Column(String(50), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    video_s3_key = Column(Text, nullable=True)
    transcript_s3_key = Column(Text, nullable=True)
    frames_s3_prefix = Column(Text, nullable=True)
    claims = Column(JSONB, nullable=True)
    verified_claims = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    client_id = Column(String(255), nullable=False, index=True)
    title = Column(Text, nullable=True)
    failed = Column(Boolean, nullable=True, default=False)


class DeviceToken(Base):
    """SQLAlchemy model for device_tokens table (push notification registration)."""
    __tablename__ = "device_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(String(255), nullable=False, index=True)
    device_token = Column(Text, nullable=False)
    sns_endpoint_arn = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# Module-level database configuration (lazy initialization)
_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker] = None


def env_var_check():
    """Check that all required database environment variables are set."""
    required_vars = ['DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_NAME']
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise ValueError(f"Missing required database environment variables: {', '.join(missing)}")


def _ensure_initialized():
    """Ensure database is initialized. Called lazily on first use."""
    global _engine, _sessionmaker
    if _engine is not None:
        return
    
    # Check env vars
    env_var_check()
    
    # Create database URL
    database_url: str = (
        f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME')}"
    )
    
    # Create engine and sessionmaker
    _engine = create_async_engine(
        database_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # Verify connections before using
        echo=False,  # Set to True for SQL query logging
    )
    _sessionmaker = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def get_engine() -> AsyncEngine:
    """Get database engine, initializing if needed."""
    _ensure_initialized()
    return _engine


def get_sessionmaker() -> async_sessionmaker:
    """Get sessionmaker, initializing if needed."""
    _ensure_initialized()
    return _sessionmaker




async def init_db():
    """Initialize SQLAlchemy async engine and session factory, create tables if they don't exist."""
    _ensure_initialized()
    try:
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        print(f"Warning: Failed to create database tables: {e}")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for getting async database session."""
    async with get_sessionmaker()() as session:
        try:
            yield session
        finally:
            await session.close()


# Async core functions (used by API with dependency injection)
async def create_job_async(session: AsyncSession, video_url: str, client_id: str) -> str:
    """Create a new job and return job_id (async, requires session).
    
    Args:
        session: Database session
        video_url: URL of the video to process
        client_id: Client ID (IDFV from iOS app) - required
    """
    job = Job(video_url=video_url, status=JobStatus.PENDING.value, client_id=client_id)
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return str(job.id)


async def update_job_status_async(session: AsyncSession, job_id: str, status: str, error_message: Optional[str] = None):
    """Update job status (async, requires session).
    
    Note: Never sets status to 'failed'. Use update_job_failed_async to mark jobs as failed.
    """
    try:
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            # Never set status to FAILED - use job.failed field instead
            if status != JobStatus.FAILED.value:
                job.status = status
            if error_message:
                job.error_message = error_message
            await session.commit()
    except Exception as e:
        await session.rollback()
        raise


async def update_job_failed_async(session: AsyncSession, job_id: str, failed: bool, error_message: Optional[str] = None):
    """Update job failed status (async, requires session).
    
    Args:
        session: Database session
        job_id: Job ID
        failed: Boolean indicating if job has failed
        error_message: Optional error message to store
    """
    try:
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            job.failed = failed
            if error_message:
                job.error_message = error_message
            await session.commit()
    except Exception as e:
        await session.rollback()
        raise


async def update_job_video_s3_key_async(session: AsyncSession, job_id: str, s3_key: str):
    """Update job with video S3 key (async, requires session)."""
    try:
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            job.video_s3_key = s3_key
            job.status = JobStatus.DOWNLOADED.value
            job.failed = False  # Clear failed flag when video is successfully uploaded
            await session.commit()
    except Exception as e:
        await session.rollback()
        raise


async def update_job_transcript_s3_key_async(session: AsyncSession, job_id: str, transcript_s3_key: str, frames_s3_prefix: str):
    """Update job with transcript and frames S3 keys (async, requires session)."""
    try:
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            job.transcript_s3_key = transcript_s3_key
            job.frames_s3_prefix = frames_s3_prefix
            job.status = JobStatus.TRANSCRIBED.value
            await session.commit()
    except Exception as e:
        await session.rollback()
        raise


async def update_job_claims_async(session: AsyncSession, job_id: str, claims: list, title: Optional[str] = None):
    """Update job with extracted claims and optional title (async, requires session)."""
    try:
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            job.claims = claims
            if title is not None:
                job.title = title
            job.status = JobStatus.CLAIMS_EXTRACTED.value
            await session.commit()
    except Exception as e:
        await session.rollback()
        raise


async def update_job_verified_claims_async(session: AsyncSession, job_id: str, verified_claims: Dict[str, Any]):
    """Update job with verified claims and mark as completed (async, requires session).
    
    New format: {title: str, verifications: [...]}
    Old format: {overall: {...}, claim_results: [...]}
    """
    try:
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            # Handle new format: extract title if present
            if "title" in verified_claims:
                job.title = verified_claims["title"]
            # Store full verified_claims structure in JSONB field
            job.verified_claims = verified_claims
            job.status = JobStatus.COMPLETED.value
            await session.commit()
    except Exception as e:
        await session.rollback()
        raise


async def get_job_async(session: AsyncSession, job_id: str) -> Optional[Dict[str, Any]]:
    """Get job by ID (async, requires session)."""
    stmt = select(Job).where(Job.id == uuid.UUID(job_id))
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()
    if job:
        return {
            "id": str(job.id),
            "video_url": job.video_url,
            "status": job.status,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "video_s3_key": job.video_s3_key,
            "transcript_s3_key": job.transcript_s3_key,
            "frames_s3_prefix": job.frames_s3_prefix,
            "claims": job.claims,
            "verified_claims": job.verified_claims,
            "error_message": job.error_message,
            "client_id": job.client_id,
            "title": job.title,
            "failed": job.failed,
        }
    return None


async def get_jobs_by_client_id_async(session: AsyncSession, client_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get jobs by client_id, ordered by created_at descending (async, requires session).
    
    Args:
        session: Database session
        client_id: Client ID to filter by
        limit: Maximum number of jobs to return (default 10)
        
    Returns:
        List of job dictionaries, ordered by created_at descending (most recent first)
    """
    stmt = (
        select(Job)
        .where(Job.client_id == client_id)
        .order_by(desc(Job.created_at))
        .limit(limit)
    )
    result = await session.execute(stmt)
    jobs = result.scalars().all()
    return [
        {
            "id": str(job.id),
            "video_url": job.video_url,
            "status": job.status,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "video_s3_key": job.video_s3_key,
            "transcript_s3_key": job.transcript_s3_key,
            "frames_s3_prefix": job.frames_s3_prefix,
            "claims": job.claims,
            "verified_claims": job.verified_claims,
            "error_message": job.error_message,
            "client_id": job.client_id,
            "title": job.title,
            "failed": job.failed,
        }
        for job in jobs
    ]


async def upsert_device_token_async(
    session: AsyncSession,
    client_id: str,
    device_token: str,
    sns_endpoint_arn: Optional[str] = None,
) -> None:
    """Insert or update device token for a client (async, requires session).
    If a row with same client_id and device_token exists, update sns_endpoint_arn and updated_at.
    """
    stmt = select(DeviceToken).where(
        DeviceToken.client_id == client_id,
        DeviceToken.device_token == device_token,
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row:
        row.sns_endpoint_arn = sns_endpoint_arn
        await session.commit()
    else:
        session.add(
            DeviceToken(
                client_id=client_id,
                device_token=device_token,
                sns_endpoint_arn=sns_endpoint_arn,
            )
        )
        await session.commit()


async def get_device_tokens_by_client_id_async(
    session: AsyncSession, client_id: str
) -> List[Dict[str, Any]]:
    """Get all device token rows for a client (async, requires session).
    Returns list of dicts with sns_endpoint_arn (and device_token); only rows with sns_endpoint_arn are useful for SNS Publish.
    """
    stmt = select(DeviceToken).where(DeviceToken.client_id == client_id)
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "client_id": r.client_id,
            "device_token": r.device_token,
            "sns_endpoint_arn": r.sns_endpoint_arn,
        }
        for r in rows
    ]


async def invalidate_device_token_by_endpoint_arn_async(
    session: AsyncSession, sns_endpoint_arn: str
) -> None:
    """Clear sns_endpoint_arn for a disabled/invalid endpoint so we stop sending to it.
    The user can re-register on next app launch to get a fresh endpoint.
    """
    stmt = select(DeviceToken).where(DeviceToken.sns_endpoint_arn == sns_endpoint_arn)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row:
        row.sns_endpoint_arn = None
        await session.commit()
