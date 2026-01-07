"""Database models and utilities for job tracking using SQLAlchemy async."""
import os
from typing import Optional, Dict, Any, AsyncGenerator, List
from sqlalchemy import Column, String, Text, DateTime, select, desc
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


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


# Module-level database configuration
def env_var_check():
    """Check that all required database environment variables are set."""
    required_vars = ['DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_NAME']
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise ValueError(f"Missing required database environment variables: {', '.join(missing)}")


# Module-level engine and sessionmaker
env_var_check()
database_url: str = (
        f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME')}"
    )
engine: AsyncEngine = create_async_engine(
            database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,  # Verify connections before using
            echo=False,  # Set to True for SQL query logging
        )
sessionmaker: async_sessionmaker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )


async def init_db():
    """Initialize SQLAlchemy async engine and session factory, create tables if they don't exist."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        print(f"Warning: Failed to create database tables: {e}")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for getting async database session."""
    async with sessionmaker() as session:
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
    job = Job(video_url=video_url, status="pending", client_id=client_id)
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return str(job.id)


async def update_job_status_async(session: AsyncSession, job_id: str, status: str, error_message: Optional[str] = None):
    """Update job status (async, requires session)."""
    try:
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            job.status = status
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
            job.status = "downloading"
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
            job.status = "processing"
            await session.commit()
    except Exception as e:
        await session.rollback()
        raise


async def update_job_claims_async(session: AsyncSession, job_id: str, claims: list):
    """Update job with extracted claims (async, requires session)."""
    try:
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            job.claims = claims
            job.status = "extracting"
            await session.commit()
    except Exception as e:
        await session.rollback()
        raise


async def update_job_verified_claims_async(session: AsyncSession, job_id: str, verified_claims: Dict[str, Any]):
    """Update job with verified claims and mark as completed (async, requires session)."""
    try:
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            job.verified_claims = verified_claims
            job.status = "completed"
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
        }
        for job in jobs
    ]
