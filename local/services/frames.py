import ffmpeg
import os


TESTS = [
    'tiktok_0',
    'instagram_0',
]

VIDEO_DIR = "local/downloads"
FRAMES_DIR = "local/data/frames"


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
        output_path = os.path.join(FRAMES_DIR, job_id)
        os.makedirs(output_path, exist_ok=True)
        temp_frame_pattern = os.path.join(output_path, 'frame_%06d.jpg')
        # (
        #     ffmpeg
        #     .input(video_path)
        #     .filter('fps', fps='1/3')  # 1 frame per 3 seconds
        #     .output(temp_frame_pattern, q=2)
        #     .overwrite_output()
        #     .run(quiet=True)
        # )
        (
            ffmpeg
            .input(video_path)
            .filter('fps', fps='2')
            .filter("select", "gt(scene,0.2)")
            .output(
                temp_frame_pattern,
                q=2,  # 'q' sets the output JPEG quality (lower is higher quality)
                fps_mode='vfr',  # variable frame rate for extracted frames
                vframes=20,
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except Exception as e:
        print(f"[{job_id}] Error extracting frames: {e}")
        return False
    else:
        return True


if __name__ == "__main__":
    for job_id in TESTS:
        parse_video(job_id)