"""SQS utilities for sending and receiving messages."""
import boto3
import json
import os
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError

_sqs_client: Optional[boto3.client] = None


def get_sqs_client():
    """Get or create SQS client."""
    global _sqs_client
    if _sqs_client is None:
        _sqs_client = boto3.client("sqs", region_name=os.getenv("AWS_REGION", "us-east-1"))
    return _sqs_client


def send_message(queue_url: str, message_body: Dict[str, Any]) -> bool:
    """Send a message to an SQS queue."""
    try:
        sqs_client = get_sqs_client()
        response = sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body),
        )
        return True
    except ClientError as e:
        print(f"Error sending message to {queue_url}: {e}")
        return False


def receive_messages(queue_url: str, max_messages: int = 1, wait_time_seconds: int = 20) -> list:
    """Receive messages from an SQS queue."""
    try:
        sqs_client = get_sqs_client()
        response = sqs_client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_time_seconds,
        )
        if "Messages" in response:
            return response["Messages"]
        return []
    except ClientError as e:
        print(f"Error receiving messages from {queue_url}: {e}")
        return []


def delete_message(queue_url: str, receipt_handle: str) -> bool:
    """Delete a message from an SQS queue."""
    try:
        sqs_client = get_sqs_client()
        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return True
    except ClientError as e:
        print(f"Error deleting message from {queue_url}: {e}")
        return False

