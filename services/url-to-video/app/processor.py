"""Video download processor (async)."""
import yt_dlp
import os
import tempfile
import sys

from shared.s3_client import upload_file
from shared.database import update_job_video_s3_key_async, update_job_status_async
from sqlalchemy.ext.asyncio import AsyncSession


async def download_video(url: str, job_id: str, session: AsyncSession) -> str:
    """
    Downloads a video from URL and uploads to S3 (async).
    
    Args:
        url: Video URL to download
        job_id: Job ID
        session: Async database session
    
    Returns:
        S3 key of the uploaded video
    """
    # Create temporary directory for download
    temp_dir = tempfile.mkdtemp()
    output_file = f"{job_id}.mp4"
    output_path = os.path.join(temp_dir, output_file)
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'quiet': True,
    }
    
    try:
        # Download video (synchronous operation - blocks event loop but acceptable)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Upload to S3 (async)
        bucket = os.getenv("VIDEO_BUCKET")
        s3_key = f"videos/{job_id}.mp4"
        
        if not await upload_file(output_path, bucket, s3_key):
            raise RuntimeError("Failed to upload video to S3")
        
        # Update job with S3 key (async)
        await update_job_video_s3_key_async(session, job_id, s3_key)
        
        # Cleanup
        os.remove(output_path)
        os.rmdir(temp_dir)
        
        return s3_key
    except Exception as e:
        # Cleanup on error
        if os.path.exists(output_path):
            os.remove(output_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
        await update_job_status_async(session, job_id, "failed", f"Failed to download video: {str(e)}")
        raise
