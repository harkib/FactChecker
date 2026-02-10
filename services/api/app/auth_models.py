"""Pydantic models for authentication requests and responses."""
from pydantic import BaseModel


class AppleSignInRequest(BaseModel):
    """Request model for Apple Sign In."""
    identity_token: str
    authorization_code: str


class AppleSignInResponse(BaseModel):
    """Response model for Apple Sign In."""
    auth_key: str
