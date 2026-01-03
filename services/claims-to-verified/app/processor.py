"""Claim verification processor (async)."""
import os
import json
import sys

from openai import AsyncOpenAI
from app.prompts import get_prompt
from shared.database import update_job_verified_claims_async, update_job_status_async
from sqlalchemy.ext.asyncio import AsyncSession


async def verify_claims(claims: list, openai_api_key: str) -> dict:
    """
    Verify claims using OpenAI API (async).
    
    Args:
        claims: List of claims to verify
        openai_api_key: OpenAI API key
    
    Returns:
        Dictionary with verification results
    """
    if not claims:
        return {
            "overall": {
                "verdict": "NOT_FACTUAL",
                "confidence": 0.0,
                "summary": "No claims to verify"
            },
            "claim_results": []
        }
    
    print(f"Verifying {len(claims)} claims...")
    
    # Call OpenAI API (async)
    client = AsyncOpenAI(api_key=openai_api_key)
    verification_response = await client.responses.create(
        model="gpt-5-nano",
        input=get_prompt(claims=claims)
    )
    verification_output = verification_response.output_text
    print(f"Verification output: {verification_output}")
    
    verification_data = json.loads(verification_output)
    return verification_data
