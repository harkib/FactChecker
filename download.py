import yt_dlp
import os
import ffmpeg
import glob
import shutil
from datetime import datetime
import whisper

DOWNLOAD_DIR = 'downloads'
DATA_DIR = 'data'

def download_tiktok(url, vedio_id=0):
    """
    Downloads a public TikTok video using yt-dlp.
    """
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    output_file = f"{vedio_id}.mp4"
    output_path = os.path.join(DOWNLOAD_DIR, output_file)
        
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'verbose': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print(f"Successfully downloaded: {url}")
    except Exception as e:
        print(f"Error downloading {url}: {e}")

    return output_path

def parse_video(video_id):
    """
    Extracts audio and frames from a video file.
    
    Args:
        video_id: The ID of the video (used to locate the video file and create output directory)
    
    Creates:
        - data/{video_id}/audio.wav: Extracted audio in WAV format
        - data/{video_id}/{timestamp}.jpg: Frame images extracted at 3-second intervals
    """
    # Check if ffmpeg is installed
    if not shutil.which('ffmpeg'):
        print("Error: ffmpeg binrary likely not installed")
        return
    
    # Construct paths
    video_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp4")
    output_dir = os.path.join(DATA_DIR, str(video_id))
    audio_path = os.path.join(output_dir, 'audio.wav')
    
    # Check if video file exists
    if not os.path.exists(video_path):
        print(f"Error: Video file not found at {video_path}")
        return
    
    # Create output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Extract audio using ffmpeg
    print(f"Extracting audio from {video_path}...")
    try:
        (
            ffmpeg
            .input(video_path)
            .output(audio_path, acodec='pcm_s16le', ar=44100, ac=2)
            .overwrite_output()
            .run(quiet=True)
        )
        print(f"Audio saved to {audio_path}")
    except ffmpeg.Error as e:
        error_message = e.stderr.decode() if e.stderr else str(e)
        print(f"Error extracting audio: {error_message}")
        return
    except FileNotFoundError:
        print("Error: ffmpeg binary not found. Please install ffmpeg.")
        return
    except Exception as e:
        print(f"Unexpected error extracting audio: {e}")
        return False
    
    # Extract frames (1 frame per 3 seconds) using ffmpeg
    print(f"Extracting frames from {video_path}...")
    try:
        # First, extract frames with sequential numbering
        temp_frame_pattern = os.path.join(output_dir, 'frame_%06d.jpg')
        (
            ffmpeg
            .input(video_path)
            .filter('fps', fps='1/3')  # 1 frame per 3 seconds
            .output(temp_frame_pattern, q=2)
            .overwrite_output()
            .run(quiet=True)
        )
        
        # Rename frames with timestamp-based names
        frame_files = sorted(glob.glob(os.path.join(output_dir, 'frame_*.jpg')))
        saved_count = 0
        for idx, frame_file in enumerate(frame_files):
            timestamp = idx * 3.0
            timestamp_str = f"{timestamp:.2f}"
            new_frame_path = os.path.join(output_dir, f"{timestamp_str}.jpg")
            os.rename(frame_file, new_frame_path)
            saved_count += 1
        
        print(f"Extracted {saved_count} frames to {output_dir}")
    except ffmpeg.Error as e:
        error_message = e.stderr.decode() if e.stderr else str(e)
        print(f"Error extracting frames: {error_message}")
    except FileNotFoundError:
        print("Error: ffmpeg binary not found. Please install ffmpeg.")
    except Exception as e:
        print(f"Error extracting frames: {e}")


    # Transcribe audio
    transcription_path = transcribe_audio(audio_path)
    print(f"Transcribed audio saved to: {transcription_path}")

def transcribe_audio(audio_path:str) -> str:
    '''
    Transcribes the audio file using whisper
    '''
    model = whisper.load_model("base")
    result = model.transcribe(audio_path)
    transcription_path = os.path.join(DATA_DIR, "transcription.txt")
    with open(transcription_path, "w") as file:
        file.write(result["text"])
    return transcription_path

def get_video_data(url:str) -> str:
    '''
    Returns the path to the video data
    '''
    video_id = int(datetime.now().timestamp())
    output_path = download_tiktok(url, vedio_id=video_id)
    parse_video(video_id)
    return os.path.join(DATA_DIR, str(video_id))

if __name__ == "__main__":
    # Example usage:
    video_url = 'https://www.tiktok.com/t/ZP8yCD5Wg/'
    # output_path = download_tiktok(video_url, vedio_id=1)
    # print(f"Downloaded video to: {output_path}")
    parse_video(1)
    # data_path = get_video_data(video_url)
    # print(f"Video data saved to: {data_path}")