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

CLAIMS_DIR = "local/data/claims"
VERIFICATIONS_DIR = "local/data/verifications"


developer = """
You are FactCheck-Verify, a verification component. You will be given a list of claims.


Goal for each claim:
- Determine verdict: SUPPORTED, NOT_SUPPORTED, PARTIALLY_SUPPORTED, MISLEADING, UNVERIFIABLE, DISPUTED, NOT_FACTUAL
    - SUPPORTED = Sufficient evidence supports the claim.
    - NOT_SUPPORTED = Insufficient evidence supports the claim.
    - PARTIALLY_SUPPORTED = Some evidence supports the claim, but not enough to be fully supported.
    - MISLEADING = The claim is technically accurate but omits context or presents information in a way that could deceive.
    - DISPUTED = Evidence conflicts, need more information to determine.
    - UNVERIFIABLE = Insufficient information to determine.
    - NOT_FACTUAL = The claim is not factual, it is an opinion or prediction.
- Provide a rationale for the verdict

Rules:
- Do not fabricate citations or details.
- If evidence conflicts, mark DISPUTED and explain what conflicts.
- Keep rationales concise and evidence-anchored.
- Output ONLY valid JSON. No markdown.

Overall verdict policy:
- Do not explicity mention "claims" in the rationale.
- Summarize (very short) the rationale for the overall verdict.
- Any key claim NOT_SUPPORTED → overall tends NOT_SUPPORTED unless clearly minor.
- Mix of SUPPORTED/NOT_SUPPORTED → PARTIALLY_SUPPORTED or DISPUTED depending on conflict.
- If most factual claims UNVERIFIABLE → overall UNVERIFIABLE.
- If input is mostly opinion/prediction with no factual claims → overall NOT_FACTUAL.

Output JSON schema:
{
  "overall": {
    "verdict": "SUPPORTED|NOT_SUPPORTED|PARTIALLY_SUPPORTED|MISLEADING|UNVERIFIABLE|DISPUTED|NOT_FACTUAL",
    "summary": "string"
  },
  "claim_results": [
    {
      "verdict": "SUPPORTED|NOT_SUPPORTED|PARTIALLY_SUPPORTED|MISLEADING|UNVERIFIABLE|DISPUTED|NOT_FACTUAL",
      "rationale": "string",
    }
  ]
}
"""

user = """
claims:
{claims}
"""

def get_prompt(claims: list[str]) -> str:
    return [
        {
            "role": "developer",
            "content": developer
        },
        {
            "role": "user",
            "content": user.format(claims='\n'.join(claims))
        }
    ]
    

async def get_verifications(job_id: str) -> bool:

    claims_path = os.path.join(CLAIMS_DIR, job_id, 'claims.json')
    with open(claims_path, 'r') as f:
        claims = json.load(f)
        claims = claims.get("claims", [])

    try:

        client = AsyncOpenAI(api_key=openai_api_key)
        verification_response = await client.responses.create(
            model="gpt-5-nano",
            tools=[{"type": "web_search"}],
            input=get_prompt(claims=claims)
        )
        verification_output = verification_response.output_text
        print(f"Verification output: {verification_output}\n")
        verification_data = json.loads(verification_output)
        print(verification_data)
 
        os.makedirs(os.path.join(VERIFICATIONS_DIR, job_id), exist_ok=True)
        with open(os.path.join(VERIFICATIONS_DIR, job_id, 'verifications.json'), 'w') as f:
            json.dump(verification_data, f)
            
    except Exception as e:
        print(f"[{job_id}] Error downloading video: {e}")
        return False
    else:
        print(f"[{job_id}] Video downloaded successfully")
        return True


if __name__ == "__main__":
    for job_id in TESTS:
        asyncio.run(get_verifications(job_id))