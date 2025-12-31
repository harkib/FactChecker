"""S3 utilities for storing and retrieving video assets."""
import boto3
import os
from typing import Optional
from botocore.exceptions import ClientError

_s3_client: Optional[boto3.client] = None


def get_s3_client():
    """Get or create S3 client."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
    return _s3_client


def upload_file(local_path: str, bucket: str, s3_key: str) -> bool:
    """Upload a file to S3."""
    try:
        s3_client = get_s3_client()
        s3_client.upload_file(local_path, bucket, s3_key)
        return True
    except ClientError as e:
        print(f"Error uploading {local_path} to s3://{bucket}/{s3_key}: {e}")
        return False


def download_file(bucket: str, s3_key: str, local_path: str) -> bool:
    """Download a file from S3."""
    try:
        s3_client = get_s3_client()
        s3_client.download_file(bucket, s3_key, local_path)
        return True
    except ClientError as e:
        print(f"Error downloading s3://{bucket}/{s3_key} to {local_path}: {e}")
        return False


def upload_bytes(data: bytes, bucket: str, s3_key: str) -> bool:
    """Upload bytes to S3."""
    try:
        s3_client = get_s3_client()
        s3_client.put_object(Bucket=bucket, Key=s3_key, Body=data)
        return True
    except ClientError as e:
        print(f"Error uploading bytes to s3://{bucket}/{s3_key}: {e}")
        return False


def list_objects(bucket: str, prefix: str) -> list:
    """List objects in S3 with given prefix."""
    try:
        s3_client = get_s3_client()
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        if "Contents" in response:
            return [obj["Key"] for obj in response["Contents"]]
        return []
    except ClientError as e:
        print(f"Error listing objects in s3://{bucket}/{prefix}: {e}")
        return []

