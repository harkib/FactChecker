"""Combined claim extraction and verification processor (async)."""
import os
import json
import base64
import tempfile
import sys
import asyncio
from typing import Dict, Any, Tuple

from openai import AsyncOpenAI
from app.prompts import get_prompt_openai, get_prompt_gemini
from shared.s3_client import download_file, list_objects
from sqlalchemy.ext.asyncio import AsyncSession


def add_citations(response):
    """
    Add citations from Gemini grounding metadata to the response text.
    
    Args:
        response: Gemini API response object with grounding_metadata
    
    Returns:
        Text with citations inserted
    """
    text = response.text
    supports = response.candidates[0].grounding_metadata.grounding_supports
    chunks = response.candidates[0].grounding_metadata.grounding_chunks

    # Sort supports by end_index in descending order to avoid shifting issues when inserting.
    sorted_supports = sorted(supports, key=lambda s: s.segment.end_index, reverse=True)

    for support in sorted_supports:
        end_index = support.segment.end_index
        if support.grounding_chunk_indices:
            # Create citation string like [title1](link1)[title2](link2)
            citation_links = []
            for i in support.grounding_chunk_indices:
                if i < len(chunks):
                    uri = chunks[i].web.uri
                    title = chunks[i].web.title
                    citation_links.append(f"[{title}]({uri})")

            citation_string = ", ".join(citation_links)
            text = text[:end_index] + citation_string + text[end_index:]

    return text


async def _download_transcript_and_frames(
    transcript_s3_key: str,
    frames_s3_prefix: str,
    assets_bucket: str
) -> Tuple[str, list]:
    """
    Download transcript and frames from S3.
    
    Returns:
        Tuple of (transcript_text, image_data_list)
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
        
        return transcript, image_data_list
    finally:
        # Cleanup temp directory
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


async def extract_and_verify_claims_openai(
    job_id: str,
    transcript_s3_key: str,
    frames_s3_prefix: str,
    assets_bucket: str,
    openai_api_key: str,
    session: AsyncSession
) -> Dict[str, Any]:
    """
    Extract and verify claims using OpenAI API (async).
    
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
    transcript, image_data_list = await _download_transcript_and_frames(
        transcript_s3_key, frames_s3_prefix, assets_bucket
    )
    
    # Call OpenAI API with web search enabled (async)
    client = AsyncOpenAI(api_key=openai_api_key)
    response = await client.responses.create(
        model="gpt-5-mini",
        tools=[{"type": "web_search"}],
        input=get_prompt_openai(transcript=transcript, image_data_list=image_data_list)
    )
    output_text = response.output_text
    print(f"Extraction and verification output: {output_text}\n")
    
    result_data = json.loads(output_text)
    
    # Validate structure
    if "title" not in result_data or "verifications" not in result_data:
        raise ValueError("Response missing required fields: title and verifications")
    
    return result_data


async def extract_and_verify_claims_gemini(
    job_id: str,
    transcript_s3_key: str,
    frames_s3_prefix: str,
    assets_bucket: str,
    gemini_api_key: str,
    session: AsyncSession
) -> Dict[str, Any]:
    """
    Extract and verify claims using Gemini API (async).
    
    Args:
        job_id: Job ID
        transcript_s3_key: S3 key of transcript file
        frames_s3_prefix: S3 prefix for frame images
        assets_bucket: S3 bucket containing assets
        gemini_api_key: Gemini API key
        session: Async database session
    
    Returns:
        Dictionary with title and verifications: {title: str, verifications: [...]}
    """
    from google import genai
    from google.genai import types
    from app.prompts import developer
    
    transcript, image_data_list = await _download_transcript_and_frames(
        transcript_s3_key, frames_s3_prefix, assets_bucket
    )
    
    # Initialize Gemini client
    client = genai.Client(api_key=gemini_api_key)
    
    # Build contents from prompt
    contents = get_prompt_gemini(transcript=transcript, image_data_list=image_data_list)
    
    # Generate content with Gemini (run sync call in executor to maintain async pattern)
    def generate_sync():
        return client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=developer,
                tools=[
                    types.Tool(
                        google_search=types.GoogleSearch()
                    )
                ]
            )
        )
    
    extraction_response = await asyncio.to_thread(generate_sync)
    extraction_text = add_citations(extraction_response)
    
    # Extract response text
    l_idx = extraction_text.find('{')
    r_idx = extraction_text.rfind('}')
    if l_idx == -1 or r_idx == -1:
        raise ValueError(f"Invalid response text: {extraction_text}")
    extraction_output = extraction_text[l_idx:r_idx+1]
    print(f"Extraction output: {extraction_output}\n")
    
    result_data = json.loads(extraction_output)
    
    # Validate structure
    if "title" not in result_data or "verifications" not in result_data:
        raise ValueError("Response missing required fields: title and verifications")
    
    return result_data


async def extract_and_verify_claims(
    job_id: str,
    transcript_s3_key: str,
    frames_s3_prefix: str,
    assets_bucket: str,
    api_key: str,
    session: AsyncSession,
    api_provider: str = None
) -> Dict[str, Any]:
    """
    Extract and verify claims from transcript and frames in one operation (async).
    Routes to appropriate provider based on API_PROVIDER environment variable.
    
    Args:
        job_id: Job ID
        transcript_s3_key: S3 key of transcript file
        frames_s3_prefix: S3 prefix for frame images
        assets_bucket: S3 bucket containing assets
        api_key: API key for the provider (OpenAI or Gemini)
        session: Async database session
        api_provider: Provider name ("openai" or "gemini"). If None, reads from API_PROVIDER env var (default: "gemini")
    
    Returns:
        Dictionary with title and verifications: {title: str, verifications: [...]}
    """
    if api_provider is None:
        api_provider = os.getenv("API_PROVIDER", "gemini").lower()
    
    print(f"Using API provider: {api_provider}")
    
    if api_provider == "openai":
        return await extract_and_verify_claims_openai(
            job_id, transcript_s3_key, frames_s3_prefix, assets_bucket, api_key, session
        )
    elif api_provider == "gemini":
        return await extract_and_verify_claims_gemini(
            job_id, transcript_s3_key, frames_s3_prefix, assets_bucket, api_key, session
        )
    else:
        raise ValueError(f"Unknown API provider: {api_provider}. Must be 'openai' or 'gemini'")
