"""ECR repositories stack."""
from aws_cdk import (
    Stack,
    aws_ecr as ecr,
    Duration,
    RemovalPolicy,
)
from constructs import Construct


class EcrStack(Stack):
    """Stack for ECR repositories."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # List of service names
        services = ["api", "url-to-video", "video-to-transcript", "transcript-to-claims", "claims-to-verified", "transcript-to-verified", "s3-video-event"]
        
        # Dictionary to store repositories
        self.repositories = {}

        for service in services:
            repo_name = f"factchecker/{service}"
            
            # Create ECR repository
            repo = ecr.Repository(
                self,
                f"{service.replace('-', '')}Repository",
                repository_name=repo_name,
                image_scan_on_push=True,
                encryption=ecr.RepositoryEncryption.AES_256,
                removal_policy=RemovalPolicy.RETAIN,  # Keep images even if stack is deleted
                lifecycle_rules=[
                    ecr.LifecycleRule(
                        description="Keep last 10 images",
                        max_image_count=10,
                    ),
                    ecr.LifecycleRule(
                        description="Expire untagged images after 7 days",
                        tag_status=ecr.TagStatus.UNTAGGED,
                        max_image_age=Duration.days(7),
                    ),
                ],
            )
            
            self.repositories[service] = repo

        # Export repository references
        self.api_repo = self.repositories["api"]
        self.url_to_video_repo = self.repositories["url-to-video"]
        self.video_to_transcript_repo = self.repositories["video-to-transcript"]
        self.transcript_to_claims_repo = self.repositories["transcript-to-claims"]
        self.claims_to_verified_repo = self.repositories["claims-to-verified"]
        self.transcript_to_verified_repo = self.repositories["transcript-to-verified"]
        self.s3_video_event_repo = self.repositories["s3-video-event"]

