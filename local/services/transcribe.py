import whisper
import os


TESTS = [
    'tiktok_0',
    'instagram_0',
]


AUDIO_DIR = "local/data/audio"
TRANSCRIPT_DIR = "local/data/transcript"


def parse_video(job_id: str) -> bool:

    try:

        audio_path = os.path.join(AUDIO_DIR, job_id, 'audio.wav')
        model = whisper.load_model("tiny")
        result = model.transcribe(audio_path)

        output_path = os.path.join(TRANSCRIPT_DIR, job_id)
        os.makedirs(output_path, exist_ok=True)
        transcript_path = os.path.join(output_path, 'transcript.txt')
        with open(transcript_path, 'w') as f:
            f.write(result['text'])

    except Exception as e:
        print(f"[{job_id}] Error transcribing audio: {e}")
        return False
    else:
        return True


if __name__ == "__main__":
    for job_id in TESTS:
        parse_video(job_id)