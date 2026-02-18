"""Pydantic models for API requests and responses."""
from pydantic import BaseModel, HttpUrl
from typing import Optional, Dict, Any, List
from datetime import datetime


class CreateJobRequest(BaseModel):
    video_url: HttpUrl

class JobResponse(BaseModel):
    id: str
    video_url: str
    status: str
    created_at: datetime
    updated_at: datetime
    video_s3_key: Optional[str] = None
    transcript_s3_key: Optional[str] = None
    frames_s3_prefix: Optional[str] = None
    claims: Optional[List[str]] = None
    verified_claims: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    client_id: str
    title: Optional[str] = None
    failed: Optional[bool] = False

    class Config:
        from_attributes = True


class CreateJobResponse(BaseModel):
    job_id: str
    status: str


class CreateUploadJobResponse(BaseModel):
    job_id: str
    upload_url: str
    expires_in: int


class GetUploadUrlResponse(BaseModel):
    upload_url: str
    expires_in: int


class RegisterDeviceTokenRequest(BaseModel):
    """Request body for POST /device-token (push notification registration)."""
    device_token: str
    sandbox: bool = False  # True for Xcode debug builds (APNS_SANDBOX)

