"""SQS utilities for sending and receiving messages (async)."""
import json
import os
from typing import Dict, Any
from botocore.exceptions import ClientError
import aioboto3


async def send_message(queue_url: str, message_body: Dict[str, Any]) -> bool:
    """Send a message to an SQS queue (async)."""
    try:
        session = aioboto3.Session()
        async with session.client("sqs", region_name=os.getenv("AWS_REGION", "us-east-1")) as sqs_client:
            await sqs_client.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(message_body),
            )
        return True
    except ClientError as e:
        print(f"Error sending message to {queue_url}: {e}")
        return False


async def receive_messages(queue_url: str, max_messages: int = 1, wait_time_seconds: int = 20) -> list:
    """Receive messages from an SQS queue (async)."""
    try:
        session = aioboto3.Session()
        async with session.client("sqs", region_name=os.getenv("AWS_REGION", "us-east-1")) as sqs_client:
            response = await sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time_seconds,
                AttributeNames=['All'],
                MessageAttributeNames=['All']
            )
            if "Messages" in response:
                return response["Messages"]
            return []
    except ClientError as e:
        print(f"Error receiving messages from {queue_url}: {e}")
        return []


async def delete_message(queue_url: str, receipt_handle: str) -> bool:
    """Delete a message from an SQS queue (async)."""
    try:
        session = aioboto3.Session()
        async with session.client("sqs", region_name=os.getenv("AWS_REGION", "us-east-1")) as sqs_client:
            await sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return True
    except ClientError as e:
        print(f"Error deleting message from {queue_url}: {e}")
        return False
