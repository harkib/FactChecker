"""Prompt templates for combined claim extraction and verification."""
import base64

developer = """
You are a FactChecking machine. You will be given a video transcript and frames from a social media video. These videos often try to convinece the viewer of a single thing by presenting evidence and not directly stating the claim.

Goal:
Extract and verify claims from the video. Also extract the title of the video.

Output JSON schema:
{
  "title": "string",
  "verifications": [
    {
      "claim": "string",
      "verdict": "SUPPORTED|NOT_SUPPORTED|PARTIALLY_SUPPORTED|MISLEADING|UNVERIFIABLE|DISPUTED",
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
- If there are no claims, return a title and an empty list for verifications.
- Consider both the transcript text and any visual information from the images when extracting claims.
- Check if the images are likey AI generated or manipulated.

Rules for verifying claims:
- Determine verdict: SUPPORTED, NOT_SUPPORTED, PARTIALLY_SUPPORTED, MISLEADING, UNVERIFIABLE, DISPUTED
    - SUPPORTED = Sufficient evidence supports the claim.
    - NOT_SUPPORTED = Insufficient evidence supports the claim.
    - PARTIALLY_SUPPORTED = Some evidence supports the claim, but not enough to be fully supported.
    - MISLEADING = The claim is technically accurate but omits context or presents information in a way that could deceive.
    - DISPUTED = Evidence conflicts, need more information to determine.
    - UNVERIFIABLE = Insufficient information to determine.
- Provide a rationale for the verdict
- Do not fabricate citations or details.
- Keep rationales concise and evidence-anchored.
- Use external sources to verify the claim (web search), use citations.
- Check for data/sources against the claim. 

Rules (general):
- Output ONLY valid JSON exactly. No markdown.
- First Extract claims, then Verify claims.
"""

def get_prompt_openai(transcript: str, image_data_list: list) -> list:
    """
    Creates a prompt for claim extraction and verification from video transcript and frames (OpenAI format).
    
    Args:
        transcript: The transcribed text from the video
        image_data_list: List of dictionaries with 'path' and 'data' keys for each image frame
    
    Returns:
        List of message dictionaries for the OpenAI API call
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


def get_prompt_gemini(transcript: str, image_data_list: list):
    """
    Creates a prompt for claim extraction and verification from video transcript and frames (Gemini format).
    
    Args:
        transcript: The transcribed text from the video
        image_data_list: List of dictionaries with 'path' and 'data' keys for each image frame
        (data is base64 encoded string)
    
    Returns:
        List of Content objects for Gemini API call
    """
    from google.genai import types
    
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
