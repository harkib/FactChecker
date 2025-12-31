"""Database models and utilities for job tracking using SQLAlchemy."""
import os
from typing import Optional, Dict, Any
from sqlalchemy import create_engine, Column, String, Text, DateTime, select
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, sessionmaker, Session
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


# SQLAlchemy engine and session factory
_engine: Optional[Any] = None
_SessionLocal: Optional[sessionmaker] = None


def init_db():
    """Initialize SQLAlchemy engine and session factory."""
    global _engine, _SessionLocal
    
    if _engine is None:
        database_url = (
            f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
            f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME')}"
        )
        
        _engine = create_engine(
            database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,  # Verify connections before using
            echo=False,  # Set to True for SQL query logging
        )
        
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=_engine
        )
    
    return _engine


def get_db_session() -> Session:
    """Get a database session."""
    if _SessionLocal is None:
        init_db()
    return _SessionLocal()


def create_job(video_url: str) -> str:
    """Create a new job and return job_id."""
    session = get_db_session()
    try:
        job = Job(video_url=video_url, status="pending")
        session.add(job)
        session.commit()
        session.refresh(job)
        return str(job.id)
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def update_job_status(job_id: str, status: str, error_message: Optional[str] = None):
    """Update job status."""
    session = get_db_session()
    try:
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        job = session.scalar(stmt)
        if job:
            job.status = status
            if error_message:
                job.error_message = error_message
            session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def update_job_video_s3_key(job_id: str, s3_key: str):
    """Update job with video S3 key."""
    session = get_db_session()
    try:
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        job = session.scalar(stmt)
        if job:
            job.video_s3_key = s3_key
            job.status = "downloading"
            session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def update_job_transcript_s3_key(job_id: str, transcript_s3_key: str, frames_s3_prefix: str):
    """Update job with transcript and frames S3 keys."""
    session = get_db_session()
    try:
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        job = session.scalar(stmt)
        if job:
            job.transcript_s3_key = transcript_s3_key
            job.frames_s3_prefix = frames_s3_prefix
            job.status = "processing"
            session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def update_job_claims(job_id: str, claims: list):
    """Update job with extracted claims."""
    session = get_db_session()
    try:
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        job = session.scalar(stmt)
        if job:
            job.claims = claims
            job.status = "extracting"
            session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def update_job_verified_claims(job_id: str, verified_claims: Dict[str, Any]):
    """Update job with verified claims and mark as completed."""
    session = get_db_session()
    try:
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        job = session.scalar(stmt)
        if job:
            job.verified_claims = verified_claims
            job.status = "completed"
            session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get job by ID."""
    session = get_db_session()
    try:
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        job = session.scalar(stmt)
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
    finally:
        session.close()
