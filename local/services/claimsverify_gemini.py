"""Video download processor (async) using Gemini API."""
from google import genai
from google.genai import types
import os
import glob
import base64
import json
from dotenv import load_dotenv
import asyncio
load_dotenv()

gemini_api_key = os.getenv("GEMINI_API_KEY")


TESTS = [
    # 'tiktok_0',
    'instagram_0',
]

TRANSCRIPT_DIR = "local/data/transcript"
FRAMES_DIR = "local/data/frames"
CLAIMVERIFY_DIR = "local/data/claim_verify"

developer = """
You are a FactChecking machine. You will be given a video transcript and frames from a social media video. These videos often try to convinece the viewer of a single thing by presenting evidence and no directly stating the claim.

Goal:
Extract and verify claims from the video. Also extract the title of the video.

Output JSON schema:
{
  "title": "string",
  "verifications": [
    {
      "claim": "string",
      "verdict": "TRUE|FALSE|PARTIALLY_TRUE|UNVERIFIABLE|DISPUTED|NOT_FACTUAL",
      "rationale": "string",
    }
  ]
}

Rules for title:
- Generate a concise title (5-15 words) that summarizes the the main claim of the video.

Rules for extracting claims:
- Extract ONLY high level claims, what is the main thing the video is trying to convey or convince the viewer of, that are potentially verifiable (facts about the world).
- Extract, ideally 1, and at most 3 claims. Conlidate claims that are related to the same topic.
- Try to keep claims less than 30 words.
- Use simple scientific wording.
- Do NOT verify, do NOT judge truth, do NOT add outside facts.
- If the input is mostly opinion/prediction, still extract any embedded factual claims.
- If there are zero factual claims, return an empty list.
- Consider both the transcript text and any visual information from the images when extracting claims.

Rules for verifying claims:
- Determine verdict: TRUE, FALSE, PARTIALLY_TRUE, UNVERIFIABLE, DISPUTED, NOT_FACTUAL
    - TRUE = Sufficient evidence to support the claim.
    - FALSE = Insufficient evidence to support the claim.
    - PARTIALLY_TRUE = Some evidence supports the claim, but not enough to be fully TRUE.
    - DISPUTED = Evidence conflicts, need more information to determine the truth of the claim.
    - UNVERIFIABLE = Insufficient information to determine the truth of the claim.
    - NOT_FACTUAL = The claim is not factual, it is an opinion or prediction.
- Provide a rationale for the verdict
- Do not fabricate citations or details.
- Keep rationales concise and evidence-anchored.
- Use external sources to verify the claim (web search), use citations.

Rules (general):
- Output ONLY valid JSON exactly. No markdown. Do not include any other text or comments. No extra formatting.
- First Extract claims, then Verify claims.
"""

def get_prompt(transcript: str, image_data_list: list) -> list:
    """
    Creates a prompt for claim extraction from video transcript and frames.
    
    Args:
        transcript: The transcribed text from the video
        image_data_list: List of dictionaries with 'path' and 'data' keys for each image frame
        (data is base64 encoded string)
    
    Returns:
        List of Content objects for Gemini API call
    """
    # Build parts list with text and images
    parts = []
    
    # Add transcript text - use direct Part constructor
    parts.append(types.Part(text=f"Transcript:\n{transcript}"))
    
    # Add images - convert base64 strings to bytes
    for img_data in image_data_list:
        # Decode base64 string to bytes
        image_bytes = base64.b64decode(img_data['data'])
        # Create Part from bytes with JPEG mime type - use direct constructor
        parts.append(types.Part(
            inline_data=types.Blob(
                data=image_bytes,
                mime_type="image/jpeg"
            )
        ))
    
    # Return list with single user Content object
    # System instruction will be passed separately in the API call
    return [
        types.Content(
            role="user",
            parts=parts
        )
    ]

def add_citations(response):
    text = response.text
    supports = response.candidates[0].grounding_metadata.grounding_supports
    chunks = response.candidates[0].grounding_metadata.grounding_chunks

    # Sort supports by end_index in descending order to avoid shifting issues when inserting.
    sorted_supports = sorted(supports, key=lambda s: s.segment.end_index, reverse=True)

    for support in sorted_supports:
        end_index = support.segment.end_index
        if support.grounding_chunk_indices:
            # Create citation string like [title1](link1)[title2](link2)
            citation_links = []
            for i in support.grounding_chunk_indices:
                if i < len(chunks):
                    uri = chunks[i].web.uri
                    title = chunks[i].web.title
                    citation_links.append(f"[{title}]({uri})")

            citation_string = ", ".join(citation_links)
            text = text[:end_index] + citation_string + text[end_index:]

    return text

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
        # Initialize Gemini client
        client = genai.Client(api_key=gemini_api_key)
        
        # Build contents from prompt
        contents = get_prompt(transcript=transcript, image_data_list=image_data_list)
        
        # Generate content with Gemini (run sync call in executor to maintain async pattern)
        # Note: Grounding/web search tools may need to be configured differently
        # For now, removing tools parameter to get basic functionality working
        def generate_sync():
            return client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=developer,
                    tools=[
                        types.Tool(
                            google_search=types.GoogleSearch()
                        )
                    ]
                )
            )
        
        extraction_response = await asyncio.to_thread(generate_sync)
        extraction_text = add_citations(extraction_response)

        # Extract response text
        l_idx = extraction_text.find('{')
        r_idx = extraction_text.rfind('}')
        if l_idx == -1 or r_idx == -1:
            raise ValueError(f"Invalid response text: {extraction_text}")
        extraction_output = extraction_text[l_idx:r_idx+1]
        # print(extraction_response.to_json_dict())
        print(f"Extraction output: {extraction_output}\n")
        extraction_data = json.loads(extraction_output)
        
        print("----- \n\n\n")
        print(json.dumps(extraction_response.to_json_dict(), indent=4))

        os.makedirs(os.path.join(CLAIMVERIFY_DIR, job_id), exist_ok=True)
        with open(os.path.join(CLAIMVERIFY_DIR, job_id, 'claims.json'), 'w') as f:
            json.dump(extraction_data, f)

    except Exception as e:
        print(f"[{job_id}] Error verifying claims with Gemini: {e}")
        return False
    else:
        print(f"[{job_id}] Claims verified successfully")
        return True


if __name__ == "__main__":
    for job_id in TESTS:
        asyncio.run(get_claims(job_id))
