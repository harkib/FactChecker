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
- Split compound statements into atomic claims.
- Preserve the original wording as much as possible.
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
    
