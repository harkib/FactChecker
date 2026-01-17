import ffmpeg
import os


TESTS = [
    # ('tiktok_0', 'local/downloads/instagram_0.mp4'),
    ('instagram_0', 'local/downloads/tiktok_0.mp4'),
]


FRAMES_DIR = "local/data/frames"


def parse_video(video_path: str, job_id: str) -> bool:
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
        temp_frame_pattern = os.path.join(FRAMES_DIR, 'frame_%06d.jpg')
        (
            ffmpeg
            .input(video_path)
            .output(
                temp_frame_pattern,
                q=2,  # 'q' sets the output JPEG quality (lower is higher quality)
                fps_mode='vfr',  # variable frame rate for extracted frames
                vf="select='gt(scene,0.1)'"
            )
            .overwrite_output()
            .run(quiet=False)
        )
    except Exception as e:
        print(f"[{job_id}] Error extracting frames: {e}")
        return False
    else:
        return True


if __name__ == "__main__":
    for job_id, url in TESTS:
        parse_video(url, job_id)