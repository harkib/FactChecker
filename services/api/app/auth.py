"""Authentication service for Apple Sign In and API Gateway API key management."""
import os
import json
import jwt
from typing import Optional
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import httpx
import aioboto3
from botocore.exceptions import ClientError
from shared.logger import get_logger

logger = get_logger("auth")

# Apple's public key endpoint
APPLE_PUBLIC_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"
APPLE_AUDIENCE = os.getenv("APPLE_CLIENT_ID")  # Should be set in environment


async def get_apple_public_keys() -> dict:
    """Fetch Apple's public keys for token verification.
    
    Returns:
        Dictionary mapping key IDs to public keys
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(APPLE_PUBLIC_KEYS_URL)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error("Failed to fetch Apple public keys", error=str(e))
        raise


def get_public_key_from_jwk(jwk: dict) -> str:
    """Convert JWK to PEM format public key.
    
    Args:
        jwk: JSON Web Key dictionary
        
    Returns:
        PEM formatted public key string
    """
    from cryptography.hazmat.primitives.asymmetric import rsa
    import base64
    
    # Extract key components (Apple uses base64url encoding)
    # jwt.utils.base64url_decode handles the URL-safe base64 decoding
    n_bytes = jwt.utils.base64url_decode(jwk["n"])
    e_bytes = jwt.utils.base64url_decode(jwk["e"])
    
    # Convert bytes to integers (big-endian)
    n = int.from_bytes(n_bytes, byteorder="big")
    e = int.from_bytes(e_bytes, byteorder="big")
    
    # Construct RSA public key
    public_key = rsa.RSAPublicNumbers(e, n).public_key(default_backend())
    
    # Serialize to PEM
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    return pem.decode("utf-8")


async def verify_apple_identity_token(identity_token: str) -> Optional[dict]:
    """Verify Apple identity token and extract claims.
    
    Args:
        identity_token: JWT identity token from Apple
        
    Returns:
        Decoded token claims if valid, None otherwise
    """
    try:
        # Decode token header to get key ID
        unverified_header = jwt.get_unverified_header(identity_token)
        kid = unverified_header.get("kid")
        
        if not kid:
            logger.warning("Token missing key ID")
            return None
        
        # Fetch Apple's public keys
        keys_response = await get_apple_public_keys()
        keys = keys_response.get("keys", [])
        
        # Find the matching key
        matching_key = None
        for key in keys:
            if key.get("kid") == kid:
                matching_key = key
                break
        
        if not matching_key:
            logger.warning("No matching public key found", kid=kid)
            return None
        
        # Convert JWK to PEM
        public_key_pem = get_public_key_from_jwk(matching_key)
        
        # Verify and decode token
        # Note: We don't verify audience here since APPLE_AUDIENCE might not be set
        # In production, you should set APPLE_CLIENT_ID and verify audience
        decoded_token = jwt.decode(
            identity_token,
            public_key_pem,
            algorithms=["RS256"],
            issuer=APPLE_ISSUER,
            audience=APPLE_AUDIENCE,  # Will be None if not set, which is okay for now
            options={"verify_aud": APPLE_AUDIENCE is not None}
        )
        
        logger.debug("Apple identity token verified successfully")
        return decoded_token
        
    except jwt.ExpiredSignatureError:
        logger.warning("Apple identity token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid Apple identity token", error=str(e))
        return None
    except Exception as e:
        logger.error("Error verifying Apple identity token", error=str(e), exc_info=True)
        return None


async def create_api_gateway_api_key(
    api_gateway_rest_api_id: str,
    usage_plan_id: str,
    description: str = "User API key from Apple Sign In"
) -> Optional[str]:
    """Create an API Gateway API key and associate it with a usage plan.
    
    Args:
        api_gateway_rest_api_id: The REST API ID
        usage_plan_id: The usage plan ID to associate with
        description: Description for the API key
        
    Returns:
        API key value if successful, None otherwise
    """
    try:
        session = aioboto3.Session()
        region = os.getenv("AWS_REGION", "us-east-1")
        
        async with session.client("apigateway", region_name=region) as apigw_client:
            # Create API key
            create_response = await apigw_client.create_api_key(
                name=f"user-key-{os.urandom(8).hex()}",
                description=description,
                enabled=True,
                generateDistinctId=True
            )
            
            api_key_id = create_response["id"]
            logger.debug("API key created", api_key_id=api_key_id)
            
            # Get the API key value (only available immediately after creation)
            get_response = await apigw_client.get_api_key(
                apiKey=api_key_id,
                includeValue=True
            )
            api_key_value = get_response["value"]
            
            # Associate API key with usage plan
            await apigw_client.create_usage_plan_key(
                usagePlanId=usage_plan_id,
                keyId=api_key_id,
                keyType="API_KEY"
            )
            
            logger.info("API key created and associated with usage plan", api_key_id=api_key_id)
            return api_key_value
            
    except ClientError as e:
        logger.error("AWS API Gateway error creating API key", error=str(e), error_code=e.response.get("Error", {}).get("Code"))
        return None
    except Exception as e:
        logger.error("Unexpected error creating API key", error=str(e), exc_info=True)
        return None
