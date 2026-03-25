"""Video download processor (async)."""
from sqlalchemy.sql.sqltypes import Boolean
import yt_dlp
import os
import tempfile
import sys
import json

TESTS = [
    ('tiktok_0', 'https://www.tiktok.com/t/ZP8yCD5Wg/'),
    ('instagram_0', 'https://www.instagram.com/reel/DR0Tkf-EvbX/?igsh=cXlzNzZzbmt2dnVu'),
    ('instagram_1', 'https://instagram.com/p/DUq3dDhEvGQ/'),
]

DOWNLOAD_DIR = "local/downloads"
DATA_DIR = "local/data"

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


def download_video(url: str, job_id: str) -> bool:


    output_path = os.path.join(DOWNLOAD_DIR, f"{job_id}.mp4")
    
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
        # 'skip_download': False,  # ensure download
        # 'forcejson': True,       # output info json after download
        'writesubtitles': False,
    }

    video_title = None

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title', None)
       
    except Exception as e:
        print(f"[{job_id}] Error downloading video: {e}")
        return False
    else:
        print(f"\n[{job_id}] Video downloaded successfully, title: {video_title}\n")
        return True

def download_image(url: str, job_id: str) -> bool:
    pass

def download_metadata(url: str, job_id: str) -> dict | None:

    ydl_opts = {
        'noplaylist': True,
        'quiet': True,
        'skip_download': True,
        'writesubtitles': False,
        "ignore_no_formats_error": True,
    }

    metadata = {}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            metadata = ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"[{job_id}] Error downloading metadata: {e}")

    else:
        print(f"\n[{job_id}] Metadata downloaded successfully\n")
        print(json.dumps(metadata, indent=4))

    return metadata

def download(url: str, job_id: str) -> bool:

    metadata = download_metadata(url, job_id)
    file_type = metadata.get('ext', None)
    if file_type == 'mp4':
        return download_video(url, job_id)
    elif file_type == 'jpg':
        return download_image(url, job_id)
    else:
        print(f"[{job_id}] Unsupported file type: {file_type}")
        return False

if __name__ == "__main__":
    for job_id, url in TESTS:
        download(url, job_id)