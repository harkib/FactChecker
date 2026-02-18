"""Lambda handler for Claims to Verified transformation (async)."""
import os
import json
import sys
import asyncio
from typing import Dict, Any, List

# Ensure /app is in Python path (fallback if PYTHONPATH env var isn't set)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

# Import modules that don't depend on secrets
from shared.logger import get_logger, bind_job_id
from shared.secrets import initialize_secrets
from shared.database import (
    get_sessionmaker,
    update_job_status_async,
    update_job_failed_async,
    update_job_verified_claims_async,
    get_job_async,
    get_device_tokens_by_client_id_async,
    invalidate_device_token_by_endpoint_arn_async,
    JobStatus,
)
from app.processor import verify_claims

# Initialize logger with resource name
logger = get_logger("claims-to-verified lambda")


def get_openai_api_key():
    """Get OpenAI API key from environment variable (injected by Lambda from Secrets Manager)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    return api_key


async def _send_push_notification_async(job_id: str, session) -> None:
    """Load job client_id, get device tokens, send SNS Publish to each endpoint. Does not raise."""
    import boto3
    job_logger = bind_job_id(logger, job_id)
    try:
        job = await get_job_async(session, job_id)
        if not job:
            return
        client_id = job.get("client_id")
        if not client_id:
            return
        tokens = await get_device_tokens_by_client_id_async(session, client_id)
        endpoints = [t["sns_endpoint_arn"] for t in tokens if t.get("sns_endpoint_arn")]
        if not endpoints:
            job_logger.debug("No device endpoints for push notification", client_id=client_id)
            return
        # APNs payload: aps.alert + optional job_id for deep link
        message_dict = {
            "aps": {
                "alert": {"title": "Fact check ready", "body": "Your fact check is complete."},
                "sound": "default",
            },
            "job_id": job_id,
        }
        message_json = json.dumps(message_dict)
        # SNS picks APNS or APNS_SANDBOX based on endpoint platform; both keys need the same payload
        sns_message = json.dumps({"APNS": message_json, "APNS_SANDBOX": message_json})
        job_logger.info(
            "Sending push notification",
            endpoints_count=len(endpoints),
            payload=message_dict,
        )
        message_attrs = {
            "AWS.SNS.MOBILE.APNS.PUSH_TYPE": {"DataType": "String", "StringValue": "alert"},
            "AWS.SNS.MOBILE.APNS.PRIORITY": {"DataType": "String", "StringValue": "10"},
        }
        region = os.getenv("AWS_REGION", "us-east-1")
        sns = boto3.client("sns", region_name=region)
        for arn in endpoints:
            try:
                sns.publish(
                    TargetArn=arn,
                    Message=sns_message,
                    MessageStructure="json",
                    MessageAttributes=message_attrs,
                )
                job_logger.debug("Push sent", endpoint_arn=arn)
            except Exception as e:
                job_logger.warning("SNS Publish failed for endpoint", endpoint_arn=arn, error=str(e))
                err_str = str(e)
                if "EndpointDisabled" in err_str or "InvalidParameter" in err_str:
                    try:
                        await invalidate_device_token_by_endpoint_arn_async(session, arn)
                        job_logger.info("Invalidated disabled endpoint", endpoint_arn=arn)
                    except Exception as inv_err:
                        job_logger.warning("Failed to invalidate endpoint", endpoint_arn=arn, error=str(inv_err))
    except Exception as e:
        job_logger.warning("Push notification failed", error=str(e))


async def process_message(message_body: dict, session) -> bool:
    """Process a single message (async)."""
    job_id = message_body.get("job_id")
    claims = message_body.get("claims", [])
    
    # Bind job_id to logger context
    job_logger = bind_job_id(logger, job_id) if job_id else logger
    
    if not job_id:
        job_logger.warning("Invalid message: missing job_id")
        return False
    
    if not claims:
        job_logger.warning("No claims provided for job")
        # Mark as completed with empty results (async)
        await update_job_verified_claims_async(session, job_id, {
            "overall": {
                "verdict": "NOT_FACTUAL",
                "confidence": 0.0,
                "summary": "No claims to verify"
            },
            "claim_results": []
        })
        await _send_push_notification_async(job_id, session)
        return True
    
    try:
        job_logger.info("Processing job: verifying claims", claims_count=len(claims))
        
        openai_api_key = get_openai_api_key()
        if not openai_api_key:
            raise ValueError("OpenAI API key not found")
        
        verified_claims = await verify_claims(claims, openai_api_key)
        
        job_logger.info("Successfully verified claims for job")
        
        # Update job with verified claims and mark as completed (async)
        await update_job_verified_claims_async(session, job_id, verified_claims)
        await _send_push_notification_async(job_id, session)
        return True
    except Exception as e:
        job_logger.error("Error processing job", exc_info=True, error=str(e))
        # Mark job as failed
        await update_job_failed_async(session, job_id, True, str(e))
        return False


async def async_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Async Lambda handler for SQS event batches.
    
    Args:
        event: SQS event with Records array
        context: Lambda context
    
    Returns:
        Dict with batchItemFailures for partial batch processing
    """
    # Initialize secrets from Secrets Manager (must happen before using database)
    await initialize_secrets()
    
    batch_item_failures: List[Dict[str, str]] = []
    
    # Process each record in the batch
    for record in event.get("Records", []):
        message_id = record.get("messageId", "")
        
        try:
            # Parse message body
            message_body = json.loads(record.get("body", "{}"))
            
            # Process message with its own database session
            async with get_sessionmaker()() as session:
                success = await process_message(message_body, session)
                
                if not success:
                    # Add to batch failures for retry
                    batch_item_failures.append({"itemIdentifier": message_id})
                    logger.warning("Failed to process message", message_id=message_id)
                else:
                    logger.info("Successfully processed message", message_id=message_id)
                    
        except json.JSONDecodeError as e:
            logger.error("Error decoding message", exc_info=True, error=str(e), message_id=message_id)
            # Invalid JSON - add to failures
            batch_item_failures.append({"itemIdentifier": message_id})
        except Exception as e:
            logger.error("Error processing message", exc_info=True, error=str(e), message_id=message_id)
            # Processing error - add to failures
            batch_item_failures.append({"itemIdentifier": message_id})
    
    # Return batch item failures for partial batch processing
    return {"batchItemFailures": batch_item_failures}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Synchronous wrapper for async handler.
    Lambda Runtime Interface Client requires a synchronous handler.
    """
    # Create a new event loop for each invocation to avoid loop conflicts
    # This ensures all async operations in this invocation use the same loop
    loop = None
    try:
        loop = asyncio.get_event_loop()
        logger.info("Using existing event loop")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.info("Created new event loop")
        
    return loop.run_until_complete(async_handler(event, context))
