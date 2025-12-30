from openai import OpenAI
from dotenv import load_dotenv
import prompts.claim_extraction as claim_extraction
import prompts.claim_verify as claim_verify
import json
import os
import glob
import base64

from download import get_video_data

load_dotenv()

# Example user input
user_input = "Blue whales are the largest animals on Earth right now. Dinosaurs were the largest animals on Earth ever."

def extract_claims(data_path, client):
    print("Step 1: Extracting claims...")
    
    # Load transcript
    # First try to find transcript in the data_path directory, then fall back to root data directory
    transcript_path = os.path.join(data_path, 'transcription.txt')
    if not os.path.exists(transcript_path):
        # Fall back to root data directory (for backwards compatibility)
        transcript_path = os.path.join('data', 'transcription.txt')
    
    if not os.path.exists(transcript_path):
        raise FileNotFoundError(f"Transcript file not found. Tried {os.path.join(data_path, 'transcription.txt')} and {os.path.join('data', 'transcription.txt')}")
    
    with open(transcript_path, 'r', encoding='utf-8') as transcript_file:
        transcript = transcript_file.read().strip()
    
    # Load all jpg files
    jpg_files = sorted(glob.glob(os.path.join(data_path, '*.jpg')))
    if not jpg_files:
        raise FileNotFoundError(f"No jpg files found in {data_path}")
    
    image_data_list = []
    for jpg_path in jpg_files:
        with open(jpg_path, 'rb') as img_file:
            img_data = base64.b64encode(img_file.read()).decode('utf-8')
            image_data_list.append({
                'path': os.path.basename(jpg_path),
                'data': img_data
            })
    
    print(f"Loaded transcript ({len(transcript)} characters) and {len(image_data_list)} image frames")
    
    # claim_prompt = claim_extraction.get_prompt(transcript=transcript, image_data_list=image_data_list)
    # print(claim_prompt[1]['content'].keys())
    # return

    extraction_response = client.responses.create(
        model="gpt-5-nano",
        input=claim_extraction.get_prompt(transcript=transcript, image_data_list=image_data_list)
    )
    extraction_output = extraction_response.output_text
    print(f"Extraction output: {extraction_output}\n")
    extraction_data = json.loads(extraction_output)
    claims = extraction_data.get("claims", [])
    notes = extraction_data.get("notes", [])
    return claims, notes

def verify_claims(claims, client):
    print("Step 2: Verifying claims...")
    verification_response = client.responses.create(
        model="gpt-5-nano",
        input=claim_verify.get_prompt(claims=claims)
    )
    verification_output = verification_response.output_text
    print(f"Verification output: {verification_output}")
    return verification_output

if __name__ == "__main__":
    print(os.getenv("OPEN_AI_API_KEY"))
    client = OpenAI(
    api_key=os.getenv("OPEN_AI_API_KEY")
    )

    # video_url = 'https://www.tiktok.com/t/ZP8yCD5Wg/'
    # video_url = 'https://vt.tiktok.com/ZS5Fd3m2e/'
    # video_data_path = get_video_data(video_url)
    video_data_path = 'data/1767055791'


    claims, notes = extract_claims(video_data_path, client)
    if not claims:
        print("No claims extracted. Notes:", notes)
    else:
        print(f"Extracted {len(claims)} claims: {claims}\n")
        verify_claims(claims, client)
