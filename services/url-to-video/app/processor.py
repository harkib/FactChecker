"""Video download processor (async)."""
import yt_dlp
import os
import tempfile
import sys
import io

import requests
from requests import Session
import aioboto3
from requests_ip_rotator import ApiGateway
from urllib.parse import urlparse
from yt_dlp.networking import RequestHandler
from yt_dlp.networking.common import Request, Response
from yt_dlp.networking.exceptions import TransportError

from shared.s3_client import upload_file
from shared.database import update_job_video_s3_key_async, update_job_status_async, JobStatus
from sqlalchemy.ext.asyncio import AsyncSession
from shared.logger import get_logger

logger = get_logger("url-to-video processor")

MAX_DURATION_SEC = 3 * 60      # hard reject
INGEST_WINDOW_SEC = 2 * 60     # only download first N seconds
MAX_FILESIZE_MB = 20           # 20 MB

# Proxy setup creates a ApiGateway that is only intended to send requests to base_url.
# Unsure if redirects to urls outside of base_url (ex graph.instagram.com) are handled by the proxy
# or back here outside of proxy, since rotating_session only captures requests to base_url. 
# Likely latter since yt-dlp needs to be involved in the parsing of response data through the process.
class RequestsRotatorRH(RequestHandler):
    """
    Custom yt-dlp RequestHandler that uses a rotating requests.Session.
    """
    _SUPPORTED_URL_SCHEMES = ('http', 'https')
    
    def __init__(self, session: Session, logger, **kwargs):
        super().__init__(logger=logger, **kwargs)
        self.session = session
        self.logger = get_logger("url-to-video RequestsRotatorRH")
    
    def _send(self, request: Request) -> Response:

        try:
            self.logger.info("Sending request", url=request.url)
            resp = self.session.request(
                method=request.method,
                url=request.url,
                headers=request.headers,
                data=request.data,
                timeout=20,
                allow_redirects=True,  # Prevent yt-dlp from seeing proxy redirected urls (ERROR: Unsupported URL)
            )
            self.logger.info("response url", url=resp.url, status=resp.status_code)
            return Response(
                fp=io.BytesIO(resp.content),
                url=resp.url,
                headers=dict(resp.headers),
                status=resp.status_code,
            )
        except requests.exceptions.RequestException as e:
            self.logger.error("Request failed", url=request.url, error=str(e))
            raise TransportError(msg=str(e), cause=e, handler=self) from e

def build_rotating_session(base_url: str, region: str = "us-east-1"):

    gateway = ApiGateway(base_url, regions=[region])
    gateway.start(force=True)
    
    session = Session()

    session.max_redirects = 30
    session.mount(base_url, gateway)
    
    return session, gateway

async def set_request_rotator_credentials():
    # Set AWS credentials from Lambda role for requests_ip_rotator
    # The library requires AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY env vars
    try:
        boto3_session = aioboto3.Session()
        credentials = await boto3_session._session.get_credentials()
        if credentials:
            os.environ['AWS_ACCESS_KEY_ID'] = credentials.access_key
            os.environ['AWS_SECRET_ACCESS_KEY'] = credentials.secret_key
            if credentials.token:
                os.environ['AWS_SESSION_TOKEN'] = credentials.token
        else:
            logger.warning("No credentials found from Lambda role")
    except Exception as e:
        logger.error("Error setting AWS credentials", exc_info=True, error=str(e))
        raise e

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

    # Set AWS credentials from Lambda role for requests_ip_rotator
    await set_request_rotator_credentials()

    # Create rotating session for IP rotation
    try:
        logger.info("Creating rotating session", url=url)
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        rotating_session, gateway = build_rotating_session(base_url)
        logger.info("Rotating session created", base_url=base_url)
    except Exception as e:
        logger.error("Error creating rotating session", exc_info=True, error=str(e))
        raise e

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
            
            # Inject custom handler for IP rotation
            ydl._request_director.handlers.clear()
            custom_handler = RequestsRotatorRH(rotating_session, logger=ydl._request_director.logger)
            ydl._request_director.add_handler(custom_handler)
            
            logger.info("Downloading video", url=url)
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
        gateway.shutdown()

        return s3_key
    except Exception as e:
        # Cleanup on error
        gateway.shutdown()
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
        raise e