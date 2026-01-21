"""Combined claim extraction and verification processor (async)."""
import os
import json
import base64
import tempfile
import sys
from typing import Dict, Any

from openai import AsyncOpenAI
from app.prompts import get_prompt
from shared.s3_client import download_file, list_objects
from sqlalchemy.ext.asyncio import AsyncSession


async def extract_and_verify_claims(
    job_id: str,
    transcript_s3_key: str,
    frames_s3_prefix: str,
    assets_bucket: str,
    openai_api_key: str,
    session: AsyncSession
) -> Dict[str, Any]:
    """
    Extract and verify claims from transcript and frames in one operation (async).
    
    Args:
        job_id: Job ID
        transcript_s3_key: S3 key of transcript file
        frames_s3_prefix: S3 prefix for frame images
        assets_bucket: S3 bucket containing assets
        openai_api_key: OpenAI API key
        session: Async database session
    
    Returns:
        Dictionary with title and verifications: {title: str, verifications: [...]}
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
        
        # Call OpenAI API with web search enabled (async)
        client = AsyncOpenAI(api_key=openai_api_key)
        response = await client.responses.create(
            model="gpt-5-mini",
            tools=[{"type": "web_search"}],
            input=get_prompt(transcript=transcript, image_data_list=image_data_list)
        )
        output_text = response.output_text
        print(f"Extraction and verification output: {output_text}\n")
        
        result_data = json.loads(output_text)
        
        # Validate structure
        if "title" not in result_data or "verifications" not in result_data:
            raise ValueError("Response missing required fields: title and verifications")
        
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)
        
        return result_data
        
    except Exception as e:
        # Cleanup on error
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise
