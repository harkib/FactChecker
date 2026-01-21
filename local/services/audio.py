import ffmpeg
import os


TESTS = [
    'tiktok_0',
    'instagram_0',
]


AUDIO_DIR = "local/data/audio"
VIDEO_DIR = "local/downloads"

def parse_video(job_id: str) -> bool:
    """
    Extract visually different (scene-change) frames from a video.
    Uses ffmpeg's select filter for scene threshold > 0.4.
    Deprecated -vsync/fps_mode=drop NOT used (use -vsync vfr instead).

    Note on ffmpeg's `q` option:
      - The parameter `q=2` in the ffmpeg output controls JPEG quality.
      - Lower values mean higher quality, with 2 being a typical good-quality setting.
      - Allowed range for JPEG is usually `2` (best) through `31` (worst).
      - `q=2` produces high-quality but not lossless (which would be a PNG).
    """
    try:
        video_path = os.path.join(VIDEO_DIR, f"{job_id}.mp4")
        output_path = os.path.join(AUDIO_DIR, job_id)
        os.makedirs(output_path, exist_ok=True)
        audio_path = os.path.join(output_path, 'audio.wav')
        (
            ffmpeg
            .input(video_path)
            .output(audio_path, acodec='pcm_s16le', ar=44100, ac=2)
            .overwrite_output()
            .run(quiet=True)
        )

    except Exception as e:
        print(f"[{job_id}] Error extracting audio: {e}")
        return False
    else:
        return True


if __name__ == "__main__":
    for job_id in TESTS:
        parse_video(job_id)