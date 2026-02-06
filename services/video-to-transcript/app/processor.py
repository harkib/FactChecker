"""Video processing to extract transcript and frames (async)."""
import ffmpeg
from ffmpeg._run import Error as FFmpegError
import whisper
import os
import glob
import tempfile
import sys

from shared.s3_client import upload_file, upload_bytes, download_file
from shared.database import update_job_transcript_s3_key_async, update_job_status_async, update_job_failed_async, JobStatus
from sqlalchemy.ext.asyncio import AsyncSession
from shared.logger import get_logger

logger = get_logger("video-to-transcript processor")


def _run_ffmpeg(ffmpeg_stream, operation_name: str, **context):
    """
    Run an ffmpeg stream and handle errors with detailed stderr logging.
    
    Args:
        ffmpeg_stream: The ffmpeg stream object (result of ffmpeg.input().output() chain)
        operation_name: Name of the operation for logging (e.g., "audio extraction", "frame extraction")
        **context: Additional context to include in error logs (e.g., video_path, audio_path)
    
    Raises:
        FFmpegError: Re-raises the original exception after logging
    """
    try:
        ffmpeg_stream.run(quiet=True)
    except FFmpegError as e:
        # Extract stderr from the exception for logging
        stderr_output = ""
        if hasattr(e, 'stderr') and e.stderr:
            try:
                stderr_output = e.stderr.decode('utf-8', errors='replace')
            except (AttributeError, UnicodeDecodeError):
                stderr_output = str(e.stderr) if e.stderr else ""
        
        logger.error(
            f"FFmpeg error during {operation_name}",
            error=str(e),
            stderr=stderr_output,
            **context
        )
        raise


async def process_video(video_s3_key: str, job_id: str, video_bucket: str, assets_bucket: str, session: AsyncSession):
    """
    Process video to extract transcript and key frames (async).
    
    Args:
        video_s3_key: S3 key of the video file
        job_id: Job ID
        video_bucket: S3 bucket containing videos
        assets_bucket: S3 bucket for transcripts and frames
        session: Async database session
    
    Returns:
        Tuple of (transcript_s3_key, frames_s3_prefix)
    """
    temp_dir = tempfile.mkdtemp()
    video_path = os.path.join(temp_dir, f"{job_id}.mp4")
    audio_path = os.path.join(temp_dir, "audio.wav")
    frames_dir = os.path.join(temp_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    whisper_cache_dir = "/tmp/whisper"
    os.makedirs(whisper_cache_dir, exist_ok=True)
    
    try:
        # Set status to PROCESSING before starting transcript extraction
        await update_job_status_async(session, job_id, JobStatus.PROCESSING.value, None)
        
        # Download video from S3 (async)
        if not await download_file(video_bucket, video_s3_key, video_path):
            raise RuntimeError("Failed to download video from S3")
        
        # Extract audio (synchronous operation - blocks event loop but acceptable)
        logger.info("Extracting audio from video...")
        _run_ffmpeg(
            ffmpeg
            .input(video_path)
            .output(audio_path, acodec='pcm_s16le', ar=44100, ac=2)
            .overwrite_output(),
            operation_name="audio extraction",
            video_path=video_path,
            audio_path=audio_path
        )
        
        # Transcribe audio
        logger.info("Transcribing audio...")
        model = whisper.load_model("tiny", download_root=whisper_cache_dir)
        result = model.transcribe(audio_path)
        transcript_text = result["text"]

        # Upload transcript to S3 (async)
        transcript_s3_key = f"transcripts/{job_id}.txt"
        if not await upload_bytes(transcript_text.encode('utf-8'), assets_bucket, transcript_s3_key):
            raise RuntimeError("Failed to upload transcript to S3")
        
        # Extract frames (1 frame per 3 seconds) (synchronous operation)
        logger.info("Extracting frames...")
        temp_frame_pattern = os.path.join(frames_dir, 'frame_%06d.jpg')
        _run_ffmpeg(
            ffmpeg
            .input(video_path)
            .filter('fps', fps='1/3')  # 1 frame per 3 seconds
            .output(temp_frame_pattern, q=2)
            .overwrite_output(),
            operation_name="frame extraction",
            video_path=video_path,
            frames_dir=frames_dir,
            frame_pattern=temp_frame_pattern
        )
        
        # Rename frames with timestamp-based names and upload to S3 (async)
        frame_files = sorted(glob.glob(os.path.join(frames_dir, 'frame_*.jpg')))
        frames_s3_prefix = f"frames/{job_id}/"
        
        for idx, frame_file in enumerate(frame_files):
            timestamp = idx * 3.0
            timestamp_str = f"{timestamp:.2f}"
            frame_s3_key = f"{frames_s3_prefix}{timestamp_str}.jpg"
            
            if not await upload_file(frame_file, assets_bucket, frame_s3_key):
                raise RuntimeError(f"Failed to upload frame {frame_s3_key} to S3")
        
        logger.info(f"Extracted {len(frame_files)} frames")
        
        # Update job with transcript and frames (async) - sets status to PROCESSING
        await update_job_transcript_s3_key_async(session, job_id, transcript_s3_key, frames_s3_prefix)
        
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)
        
        return transcript_s3_key, frames_s3_prefix
        
    except Exception as e:
        # Cleanup on error
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        # Mark job as failed
        await update_job_failed_async(session, job_id, True, f"Failed to process video: {str(e)}")
        raise
