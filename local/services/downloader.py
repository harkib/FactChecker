"""Video download processor (async)."""
from sqlalchemy.sql.sqltypes import Boolean
import yt_dlp
import os
import tempfile
import sys

DOWNLOAD_DIR = "local/downloads"
DATA_DIR = "local/data"

TESTS = [
    # ('tiktok_0', 'https://www.tiktok.com/t/ZP8yCD5Wg/'),
    ('instagram_0', 'https://www.instagram.com/reel/DR0Tkf-EvbX/?igsh=cXlzNzZzbmt2dnVu'),
]
def download_video(url: str, job_id: str) -> bool:


    output_path = os.path.join(DOWNLOAD_DIR, f"{job_id}.mp4")
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'quiet': True,
    }
    
    try:

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
       
    except Exception as e:
        print(f"[{job_id}] Error downloading video: {e}")
        return False
    else:
        print(f"[{job_id}] Video downloaded successfully")
        return True


if __name__ == "__main__":
    for job_id, url in TESTS:
        download_video(url, job_id)