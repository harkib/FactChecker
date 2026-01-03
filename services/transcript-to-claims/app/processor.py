"""Claim extraction processor (async)."""
import os
import json
import base64
import tempfile
import sys

from openai import AsyncOpenAI
from app.prompts import get_prompt
from shared.s3_client import download_file, list_objects
from shared.database import update_job_claims_async, update_job_status_async
from sqlalchemy.ext.asyncio import AsyncSession


async def extract_claims(job_id: str, transcript_s3_key: str, frames_s3_prefix: str, assets_bucket: str, openai_api_key: str, session: AsyncSession) -> list:
    """
    Extract claims from transcript and frames (async).
    
    Args:
        job_id: Job ID
        transcript_s3_key: S3 key of transcript file
        frames_s3_prefix: S3 prefix for frame images
        assets_bucket: S3 bucket containing assets
        openai_api_key: OpenAI API key
        session: Async database session
    
    Returns:
        List of extracted claims
    """
    temp_dir = tempfile.mkdtemp()
    transcript_path = os.path.join(temp_dir, "transcript.txt")
    
    try:
        # Download transcript from S3 (async)
        if not await download_file(assets_bucket, transcript_s3_key, transcript_path):
            raise RuntimeError("Failed to download transcript from S3")
        
        with open(transcript_path, 'r', encoding='utf-8') as f:
            transcript = f.read().strip()
        
        # List and download frame images (async)
        frame_keys = await list_objects(assets_bucket, frames_s3_prefix)
        frame_keys.sort()  # Sort by timestamp
        
        image_data_list = []
        for frame_key in frame_keys:
            frame_path = os.path.join(temp_dir, os.path.basename(frame_key))
            if await download_file(assets_bucket, frame_key, frame_path):
                with open(frame_path, 'rb') as img_file:
                    img_data = base64.b64encode(img_file.read()).decode('utf-8')
                    image_data_list.append({
                        'path': os.path.basename(frame_key),
                        'data': img_data
                    })
        
        if not image_data_list:
            raise RuntimeError("No frame images found")
        
        print(f"Loaded transcript ({len(transcript)} characters) and {len(image_data_list)} image frames")
        
        # Call OpenAI API (async)
        client = AsyncOpenAI(api_key=openai_api_key)
        extraction_response = await client.responses.create(
            model="gpt-5-nano",
            input=get_prompt(transcript=transcript, image_data_list=image_data_list)
        )
        extraction_output = extraction_response.output_text
        print(f"Extraction output: {extraction_output}\n")
        
        extraction_data = json.loads(extraction_output)
        claims = extraction_data.get("claims", [])
        notes = extraction_data.get("notes", [])
        
        if notes:
            print(f"Notes: {notes}")
        
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)
        
        return claims
        
    except Exception as e:
        # Cleanup on error
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise
