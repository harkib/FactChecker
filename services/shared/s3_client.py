"""S3 utilities for storing and retrieving video assets (async)."""
import os
from typing import Optional
from botocore.exceptions import ClientError
import aioboto3


async def upload_file(local_path: str, bucket: str, s3_key: str) -> bool:
    """Upload a file to S3 (async)."""
    try:
        session = aioboto3.Session()
        async with session.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1")) as s3_client:
            with open(local_path, 'rb') as f:
                await s3_client.upload_fileobj(f, bucket, s3_key)
        return True
    except ClientError as e:
        print(f"Error uploading {local_path} to s3://{bucket}/{s3_key}: {e}")
        return False
    except Exception as e:
        print(f"Error uploading {local_path} to s3://{bucket}/{s3_key}: {e}")
        return False


async def download_file(bucket: str, s3_key: str, local_path: str) -> bool:
    """Download a file from S3 (async)."""
    try:
        session = aioboto3.Session()
        async with session.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1")) as s3_client:
            # Ensure directory exists
            dir_path = os.path.dirname(local_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with open(local_path, 'wb') as f:
                response = await s3_client.get_object(Bucket=bucket, Key=s3_key)
                async for chunk in response['Body']:
                    f.write(chunk)
        return True
    except ClientError as e:
        print(f"Error downloading s3://{bucket}/{s3_key} to {local_path}: {e}")
        return False
    except Exception as e:
        print(f"Error downloading s3://{bucket}/{s3_key} to {local_path}: {e}")
        return False


async def upload_bytes(data: bytes, bucket: str, s3_key: str) -> bool:
    """Upload bytes to S3 (async)."""
    try:
        session = aioboto3.Session()
        async with session.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1")) as s3_client:
            await s3_client.put_object(Bucket=bucket, Key=s3_key, Body=data)
        return True
    except ClientError as e:
        print(f"Error uploading bytes to s3://{bucket}/{s3_key}: {e}")
        return False
    except Exception as e:
        print(f"Error uploading bytes to s3://{bucket}/{s3_key}: {e}")
        return False


async def list_objects(bucket: str, prefix: str) -> list:
    """List objects in S3 with given prefix (async)."""
    try:
        session = aioboto3.Session()
        async with session.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1")) as s3_client:
            response = await s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
            if "Contents" in response:
                return [obj["Key"] for obj in response["Contents"]]
            return []
    except ClientError as e:
        print(f"Error listing objects in s3://{bucket}/{prefix}: {e}")
        return []
    except Exception as e:
        print(f"Error listing objects in s3://{bucket}/{prefix}: {e}")
        return []
