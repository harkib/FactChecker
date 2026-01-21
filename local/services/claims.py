"""Video download processor (async)."""
from openai import AsyncOpenAI
import os
import glob
import base64
import json
from dotenv import load_dotenv
import asyncio
load_dotenv()

openai_api_key = os.getenv("OPEN_AI_API_KEY")


TESTS = [
    # 'tiktok_0',
    'instagram_0',
]

TRANSCRIPT_DIR = "local/data/transcript"
FRAMES_DIR = "local/data/frames"
CLAIMS_DIR = "local/data/claims"

developer = """
You are FactCheck-Extract, a careful claim extraction component.

Goal:
Turn the user input into a list of atomic, checkable claims.

Output JSON schema:
{
  "claims": ["string", "..."],
  "notes": ["string", "..."]
}

Rules:
- Extract ONLY claims that are potentially verifiable (facts about the world).
- Extract at most 3 claims. Conlidate claims that are related to the same topic.
- Try to keep claims less than 30 words. 
- Try to perserve key words and phrases from the original statement.
- Use simple scientific wording.
- Do NOT verify, do NOT judge truth, do NOT add outside facts.
- If the input is mostly opinion/prediction, still extract any embedded factual claims.
- If there are zero factual claims, return an empty list for "claims" and a note for "notes".
- Output ONLY valid JSON exactly. No markdown.
- Consider both the transcript text and any visual information from the images when extracting claims.
"""

def get_prompt(transcript: str, image_data_list: list) -> list:
    """
    Creates a prompt for claim extraction from video transcript and frames.
    
    Args:
        transcript: The transcribed text from the video
        image_data_list: List of dictionaries with 'path' and 'data' keys for each image frame
    
    Returns:
        List of message dictionaries for the API call
    """
    # Build image content list
    image_content = []
    for img_data in image_data_list:
        image_content.append({
            "type": "input_image",
            "image_url": f"data:image/jpeg;base64,{img_data['data']}",
        })
    
    # Build user message with transcript and images
    user_content = [
        {
            "type": "input_text",
            "text": f"Transcript:\n{transcript}"
        }
    ]
    user_content.extend(image_content)
    
    return [
        {
            "role": "developer",
            "content": developer
        },
        {
            "role": "user",
            "content": user_content
        }
    ]
    



async def get_claims(job_id: str) -> bool:

    transcript_path = os.path.join(TRANSCRIPT_DIR, job_id, 'transcript.txt')
    with open(transcript_path, 'r') as f:
        transcript = f.read()

    frames_path = os.path.join(FRAMES_DIR, job_id)
    image_data_list = []
    for img_path in glob.glob(os.path.join(frames_path, '*.jpg')):
        with open(img_path, 'rb') as f:
            image_data_list.append({
                'path': img_path,
                'data': base64.b64encode(f.read()).decode('utf-8')
            })

    try:

        client = AsyncOpenAI(api_key=openai_api_key)
        extraction_response = await client.responses.create(
            model="gpt-5-nano",
            input=get_prompt(transcript=transcript, image_data_list=image_data_list)
        )
        extraction_output = extraction_response.output_text
        print(f"Extraction output: {extraction_output}\n")
        extraction_data = json.loads(extraction_output)
        print(extraction_data)

        os.makedirs(os.path.join(CLAIMS_DIR, job_id), exist_ok=True)
        with open(os.path.join(CLAIMS_DIR, job_id, 'claims.json'), 'w') as f:
            json.dump(extraction_data, f)

    except Exception as e:
        print(f"[{job_id}] Error downloading video: {e}")
        return False
    else:
        print(f"[{job_id}] Video downloaded successfully")
        return True


if __name__ == "__main__":
    for job_id in TESTS:
        asyncio.run(get_claims(job_id))