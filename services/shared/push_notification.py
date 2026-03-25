"""Push notification utilities via AWS SNS."""
import json
import boto3

from shared.env import get_env
from shared.database import get_job_async, get_device_tokens_by_client_id_async, invalidate_device_token_by_endpoint_arn_async


async def send_push_notification(job_id: str, session, logger, title: str = "Gut check ready", body: str = "") -> None:
    """Send APNs push notification to all devices registered for the job's client.

    Does not raise — errors are logged and swallowed so the caller's flow is not interrupted.
    """
    from shared.logger import bind_job_id
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

        message_dict = {
            "aps": {
                "alert": {"title": title, "body": body},
                "sound": "default",
            },
            "job_id": job_id,
        }
        message_json = json.dumps(message_dict)
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
        region = get_env("AWS_REGION", "us-east-1")
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
