"""S3 storage stack."""
from aws_cdk import (
    Stack,
    Duration,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_lambda as lambda_,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    aws_ecr as ecr,
    RemovalPolicy,
)
from constructs import Construct
from typing import Optional


class StorageStack(Stack):
    """Stack for S3 buckets."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: Optional[ec2.IVpc] = None,
        database_secret: Optional[secretsmanager.ISecret] = None,
        database_endpoint: Optional[str] = None,
        video_to_transcript_queue_url: Optional[str] = None,
        video_to_transcript_queue_arn: Optional[str] = None,
        s3_event_repository: Optional[ecr.IRepository] = None,
        **kwargs
    ) -> None:
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
        
        # Create S3 event handler Lambda if all required parameters are provided
        if (vpc and database_secret and database_endpoint and 
            video_to_transcript_queue_url and s3_event_repository):
            self._create_s3_event_handler(
                vpc,
                database_secret,
                database_endpoint,
                video_to_transcript_queue_url,
                video_to_transcript_queue_arn,
                s3_event_repository,
            )
        else:
            self.s3_event_lambda = None

        # Lifecycle rules (optional - uncomment if needed)
        # self.video_bucket.add_lifecycle_rule(
        #     id="DeleteOldVideos",
        #     expiration=Duration.days(30),
        # )

    def _create_s3_event_handler(
        self,
        vpc: ec2.IVpc,
        database_secret: secretsmanager.ISecret,
        database_endpoint: str,
        video_to_transcript_queue_url: str,
        video_to_transcript_queue_arn: Optional[str],
        repository: ecr.IRepository,
    ):
        """Create S3 event handler Lambda and configure event notification."""
        # Create Lambda execution role
        lambda_role = iam.Role(
            self,
            "S3VideoEventHandlerLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                ),
            ],
        )

        # Grant S3 permissions
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject"],
                resources=[f"{self.video_bucket.bucket_arn}/*"],
            )
        )

        # Grant SQS send permissions
        if video_to_transcript_queue_arn:
            lambda_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["sqs:SendMessage"],
                    resources=[video_to_transcript_queue_arn],
                )
            )
        else:
            # Fallback to wildcard if ARN not provided
            lambda_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["sqs:SendMessage"],
                    resources=["*"],
                )
            )

        # Grant RDS permissions
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["rds-db:connect"],
                resources=[f"arn:aws:rds-db:{self.region}:{self.account}:dbuser:*/postgres"],
            )
        )

        # Grant Secrets Manager permissions
        database_secret_arn_pattern = f"{database_secret.secret_arn}-*"
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["secretsmanager:GetSecretValue"],
                resources=[database_secret.secret_arn, database_secret_arn_pattern],
            )
        )

        # Add database connection info to environment
        env = {
            "VIDEO_TO_TRANSCRIPT_QUEUE_URL": video_to_transcript_queue_url,
            "DB_HOST": database_endpoint,
            "DB_PORT": "5432",
            "DB_NAME": "factchecker",
        }

        # Get private subnets for VPC configuration
        private_subnets = vpc.private_subnets

        # Create security group for Lambda
        lambda_sg = ec2.SecurityGroup(
            self,
            "S3VideoEventHandlerLambdaSecurityGroup",
            vpc=vpc,
            description="Security group for S3 Video Event Handler Lambda",
            allow_all_outbound=True,
        )

        # Create Lambda function using container image
        self.s3_event_lambda = lambda_.DockerImageFunction(
            self,
            "S3VideoEventHandlerLambda",
            code=lambda_.DockerImageCode.from_ecr(
                repository=repository,
                tag_or_digest="latest",
            ),
            function_name="factchecker-s3-video-event",
            role=lambda_role,
            timeout=Duration.minutes(5),
            memory_size=512,
            environment=env,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=private_subnets),
            security_groups=[lambda_sg],
        )

        # Add secrets as environment variables
        self.s3_event_lambda.add_environment("DB_SECRET_ARN", database_secret.secret_arn)

        # Configure S3 event notification
        # Filter for videos/*.mp4 files only
        self.video_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(self.s3_event_lambda),
            s3.NotificationKeyFilter(prefix="videos/", suffix=".mp4")
        )
