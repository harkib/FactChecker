"""Database models and utilities for job tracking using SQLAlchemy async."""
import os
import asyncio
from typing import Optional, Dict, Any, AsyncGenerator
from sqlalchemy import Column, String, Text, DateTime, select
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
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


# SQLAlchemy async engine and session factory
_engine: Optional[Any] = None
_AsyncSessionLocal: Optional[async_sessionmaker] = None


async def _init_db_async():
    """Initialize SQLAlchemy async engine and session factory, create tables if they don't exist."""
    global _engine, _AsyncSessionLocal
    
    if _engine is None:
        database_url = (
            f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
            f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME')}"
        )
        
        _engine = create_async_engine(
            database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,  # Verify connections before using
            echo=False,  # Set to True for SQL query logging
        )
        
        _AsyncSessionLocal = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        # Create tables if they don't exist
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    return _engine


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for getting async database session."""
    if _AsyncSessionLocal is None:
        await _init_db_async()
    
    async with _AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def init_db():
    """Synchronous wrapper for init_db (for worker services)."""
    if _AsyncSessionLocal is None:
        asyncio.run(_init_db_async())


# Export async version for API use
init_db_async = _init_db_async


# Async core functions (used by API with dependency injection)
async def _create_job_async(session: AsyncSession, video_url: str) -> str:
    """Create a new job and return job_id (async, requires session)."""
    job = Job(video_url=video_url, status="pending")
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return str(job.id)


async def _update_job_status_async(session: AsyncSession, job_id: str, status: str, error_message: Optional[str] = None):
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


async def _update_job_video_s3_key_async(session: AsyncSession, job_id: str, s3_key: str):
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


async def _update_job_transcript_s3_key_async(session: AsyncSession, job_id: str, transcript_s3_key: str, frames_s3_prefix: str):
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


async def _update_job_claims_async(session: AsyncSession, job_id: str, claims: list):
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


async def _update_job_verified_claims_async(session: AsyncSession, job_id: str, verified_claims: Dict[str, Any]):
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


async def _get_job_async(session: AsyncSession, job_id: str) -> Optional[Dict[str, Any]]:
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
        }
    return None


# Synchronous wrapper functions for worker services (original function names for backward compatibility)
def create_job(video_url: str) -> str:
    """Create a new job and return job_id (sync wrapper for workers)."""
    init_db()
    async def _create():
        async with _AsyncSessionLocal() as session:
            return await _create_job_async(session, video_url)
    return asyncio.run(_create())


def update_job_status(job_id: str, status: str, error_message: Optional[str] = None):
    """Update job status (sync wrapper for workers)."""
    init_db()
    async def _update():
        async with _AsyncSessionLocal() as session:
            await _update_job_status_async(session, job_id, status, error_message)
    asyncio.run(_update())


def update_job_video_s3_key(job_id: str, s3_key: str):
    """Update job with video S3 key (sync wrapper for workers)."""
    init_db()
    async def _update():
        async with _AsyncSessionLocal() as session:
            await _update_job_video_s3_key_async(session, job_id, s3_key)
    asyncio.run(_update())


def update_job_transcript_s3_key(job_id: str, transcript_s3_key: str, frames_s3_prefix: str):
    """Update job with transcript and frames S3 keys (sync wrapper for workers)."""
    init_db()
    async def _update():
        async with _AsyncSessionLocal() as session:
            await _update_job_transcript_s3_key_async(session, job_id, transcript_s3_key, frames_s3_prefix)
    asyncio.run(_update())


def update_job_claims(job_id: str, claims: list):
    """Update job with extracted claims (sync wrapper for workers)."""
    init_db()
    async def _update():
        async with _AsyncSessionLocal() as session:
            await _update_job_claims_async(session, job_id, claims)
    asyncio.run(_update())


def update_job_verified_claims(job_id: str, verified_claims: Dict[str, Any]):
    """Update job with verified claims and mark as completed (sync wrapper for workers)."""
    init_db()
    async def _update():
        async with _AsyncSessionLocal() as session:
            await _update_job_verified_claims_async(session, job_id, verified_claims)
    asyncio.run(_update())


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get job by ID (sync wrapper for workers)."""
    init_db()
    async def _get():
        async with _AsyncSessionLocal() as session:
            return await _get_job_async(session, job_id)
    return asyncio.run(_get())


# Export async versions for API use (with cleaner names)
init_db_async = _init_db_async
create_job_async = _create_job_async
update_job_status_async = _update_job_status_async
update_job_video_s3_key_async = _update_job_video_s3_key_async
update_job_transcript_s3_key_async = _update_job_transcript_s3_key_async
update_job_claims_async = _update_job_claims_async
update_job_verified_claims_async = _update_job_verified_claims_async
get_job_async = _get_job_async
