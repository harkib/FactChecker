"""S3 storage stack."""
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    RemovalPolicy,
)
from constructs import Construct


class StorageStack(Stack):
    """Stack for S3 buckets."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 bucket for video storage
        self.video_bucket = s3.Bucket(
            self,
            "VideoBucket",
            bucket_name=f"factchecker-videos-{self.account}-{self.region}",
            removal_policy=RemovalPolicy.DESTROY,  # Change for production
            auto_delete_objects=True,  # Change for production
            versioned=False,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        # S3 bucket for transcripts and frames
        self.assets_bucket = s3.Bucket(
            self,
            "AssetsBucket",
            bucket_name=f"factchecker-assets-{self.account}-{self.region}",
            removal_policy=RemovalPolicy.DESTROY,  # Change for production
            auto_delete_objects=True,  # Change for production
            versioned=False,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        # Lifecycle rules (optional - uncomment if needed)
        # self.video_bucket.add_lifecycle_rule(
        #     id="DeleteOldVideos",
        #     expiration=Duration.days(30),
        # )

