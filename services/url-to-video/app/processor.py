"""Video download processor (async)."""
import yt_dlp
import os
import tempfile
import sys

from shared.s3_client import upload_file
from shared.database import update_job_video_s3_key_async, update_job_status_async, JobStatus
from sqlalchemy.ext.asyncio import AsyncSession

MAX_DURATION_SEC = 3 * 60      # hard reject
INGEST_WINDOW_SEC = 2 * 60     # only download first N seconds
MAX_FILESIZE_MB = 20           # 20 MB

def duration_filter(info):
    """
    yt-dlp match_filter callback
    Return None to allow download, or a string to reject.
    """
    duration = info.get("duration")

    if duration is None:
        return "Rejected: unknown duration"

    if duration > MAX_DURATION_SEC:
        return f"Rejected: duration {duration}s exceeds {MAX_DURATION_SEC}s"

    return None
    
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
        "match_filter": duration_filter,
        "download_sections": f"*0-{INGEST_WINDOW_SEC}",
        "max_filesize": MAX_FILESIZE_MB * 1024 * 1024,
        "concurrent_fragments": 1, # looks less like scraping
    }
    
    try:
        # Set status to DOWNLOADING before starting download
        await update_job_status_async(session, job_id, JobStatus.DOWNLOADING.value, None)
        
        # Download video (synchronous operation - blocks event loop but acceptable)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Upload to S3 (async)
        bucket = os.getenv("VIDEO_BUCKET")
        s3_key = f"videos/{job_id}.mp4"
        
        if not await upload_file(output_path, bucket, s3_key):
            raise RuntimeError("Failed to upload video to S3")
        
        # Update job with S3 key (async) - sets status to DOWNLOADED
        await update_job_video_s3_key_async(session, job_id, s3_key)
        

        
        # Cleanup
        os.remove(output_path)
        os.rmdir(temp_dir)
        
        return s3_key
    except Exception as e:
        # Cleanup on error
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        if os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except:
                pass
        # Don't update job status here - let the caller handle it
        # This avoids double updates and potential event loop conflicts
        raise e
