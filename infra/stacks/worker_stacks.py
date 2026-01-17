"""Worker ECS services and Lambda functions stack."""
from typing import Dict, Optional
from aws_cdk import (
    Stack,
    Duration,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_lambda_event_sources as lambda_event_sources,
    aws_rds as rds,
    aws_sqs as sqs,
    aws_secretsmanager as secretsmanager,
    # aws_applicationautoscaling as appscaling,  # Unused - CloudWatch metrics disabled
    # aws_cloudwatch as cloudwatch,  # Unused - CloudWatch metrics disabled
)
from constructs import Construct


class WorkerStacks(Stack):
    """Stack for worker ECS services."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        cluster: ecs.Cluster,
        database_secret: secretsmanager.ISecret,
        database_endpoint: str,
        database_instance: rds.IDatabaseInstance = None,
        video_bucket_name: str = None,
        assets_bucket_name: str = None,
        url_to_video_queue: sqs.IQueue = None,
        url_to_video_queue_url: str = None,
        video_to_transcript_queue: sqs.IQueue = None,
        video_to_transcript_queue_url: str = None,
        transcript_to_claims_queue: sqs.IQueue = None,
        transcript_to_claims_queue_url: str = None,
        claims_to_verified_queue: sqs.IQueue = None,
        claims_to_verified_queue_url: str = None,
        url_to_video_queue_arn: str = None,
        video_to_transcript_queue_arn: str = None,
        transcript_to_claims_queue_arn: str = None,
        claims_to_verified_queue_arn: str = None,
        ecr_repositories: Dict[str, ecr.IRepository] = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Store database endpoint and instance for use in worker services
        self.database_endpoint = database_endpoint
        self.database_instance = database_instance

        # Get OpenAI secret
        openai_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "OpenAISecret", "factchecker/openai-api-key"
        )

        # Common execution role for all workers
        execution_role = iam.Role(
            self,
            "WorkerExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )

        # Grant Secrets Manager permissions to execution role
        # Note: OpenAI secret uses from_secret_name_v2 which returns partial ARN without suffix
        # AWS Secrets Manager adds a random 6-character suffix, so we need wildcard for OpenAI secret
        openai_secret_arn_pattern = f"{openai_secret.secret_arn}-*"
        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["secretsmanager:GetSecretValue"],
                resources=[database_secret.secret_arn, openai_secret_arn_pattern],
            )
        )

        # URL to Video Worker - Lambda function
        if url_to_video_queue:
            self._create_lambda_worker(
                "UrlToVideoWorker",
                "url-to-video",
                vpc,
                database_secret,
                openai_secret,
                {
                    "URL_TO_VIDEO_QUEUE_URL": url_to_video_queue_url,
                    "VIDEO_BUCKET": video_bucket_name,
                    "VIDEO_TO_TRANSCRIPT_QUEUE_URL": video_to_transcript_queue_url,
                },
                queue=url_to_video_queue,
                queue_arn=url_to_video_queue_arn,
                memory=1024,
                repository=ecr_repositories["url-to-video"],
            )

        # Video to Transcript Worker - Lambda function
        if video_to_transcript_queue:
            self._create_lambda_worker(
                "VideoToTranscriptWorker",
                "video-to-transcript",
                vpc,
                database_secret,
                openai_secret,
                {
                    "VIDEO_TO_TRANSCRIPT_QUEUE_URL": video_to_transcript_queue_url,
                    "VIDEO_BUCKET": video_bucket_name,
                    "ASSETS_BUCKET": assets_bucket_name,
                    "TRANSCRIPT_TO_CLAIMS_QUEUE_URL": transcript_to_claims_queue_url,
                },
                queue=video_to_transcript_queue,
                queue_arn=video_to_transcript_queue_arn,
                memory=3008,  # Max memory for Lambda with VPC configuration
                repository=ecr_repositories["video-to-transcript"],
            )

        # Transcript to Claims Worker - Lambda function
        if transcript_to_claims_queue:
            self._create_lambda_worker(
                "TranscriptToClaimsWorker",
                "transcript-to-claims",
                vpc,
                database_secret,
                openai_secret,
                {
                    "TRANSCRIPT_TO_CLAIMS_QUEUE_URL": transcript_to_claims_queue_url,
                    "ASSETS_BUCKET": assets_bucket_name,
                    "CLAIMS_TO_VERIFIED_QUEUE_URL": claims_to_verified_queue_url,
                },
                queue=transcript_to_claims_queue,
                queue_arn=transcript_to_claims_queue_arn,
                memory=2048,
                repository=ecr_repositories["transcript-to-claims"],
            )

        # Claims to Verified Worker - Lambda function
        if claims_to_verified_queue:
            self._create_lambda_worker(
                "ClaimsToVerifiedWorker",
                "claims-to-verified",
                vpc,
                database_secret,
                openai_secret,
                {
                    "CLAIMS_TO_VERIFIED_QUEUE_URL": claims_to_verified_queue_url,
                },
                queue=claims_to_verified_queue,
                queue_arn=claims_to_verified_queue_arn,
                memory=1024,
                repository=ecr_repositories["claims-to-verified"],
            )

    def _create_worker_service(
        self,
        service_id: str,
        cluster: ecs.Cluster,
        service_name: str,
        execution_role: iam.Role,
        database_secret: secretsmanager.ISecret,
        openai_secret: secretsmanager.ISecret,
        environment: dict,
        queue_url: str,
        queue_arn: str,
        cpu: int,
        memory: int,
        repository: ecr.IRepository,
    ):
        """Create a worker ECS service."""
        # Create task role
        task_role = iam.Role(
            self,
            f"{service_id}TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        # Grant SQS permissions
        # Note: Using all SQS actions needed for receiving and processing messages
        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                    "sqs:GetQueueUrl",
                    "sqs:ChangeMessageVisibility",
                ],
                resources=[queue_arn],
            )
        )

        # Grant S3 permissions
        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                resources=["*"],  # Restrict to specific buckets in production
            )
        )

        # Grant SQS send permissions (for next queue in pipeline)
        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["sqs:SendMessage"],
                resources=["*"],  # Restrict to specific queues in production
            )
        )

        # Grant RDS permissions
        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["rds-db:connect"],
                resources=[f"arn:aws:rds-db:{self.region}:{self.account}:dbuser:*/postgres"],
            )
        )

        # Grant Secrets Manager permissions
        # Note: OpenAI secret uses from_secret_name_v2 which returns partial ARN without suffix
        # AWS Secrets Manager adds a random 6-character suffix, so we need wildcard for OpenAI secret
        openai_secret_arn_pattern = f"{openai_secret.secret_arn}-*"
        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["secretsmanager:GetSecretValue"],
                resources=[database_secret.secret_arn, openai_secret_arn_pattern],
            )
        )

        # Add database connection info to environment
        env = {
            **environment,
            "DB_HOST": self.database_endpoint,
            "DB_PORT": "5432",
            "DB_NAME": "factchecker",
        }

        # Create task definition
        task_definition = ecs.FargateTaskDefinition(
            self,
            f"{service_id}TaskDef",
            cpu=cpu,
            memory_limit_mib=memory,
            task_role=task_role,
            execution_role=execution_role,
        )

        # Add container
        container = task_definition.add_container(
            f"{service_id}Container",
            image=ecs.ContainerImage.from_ecr_repository(
                repository, "latest"
            ),
            environment=env,
            secrets={
                "DB_USER": ecs.Secret.from_secrets_manager(database_secret, "username"),
                "DB_PASSWORD": ecs.Secret.from_secrets_manager(database_secret, "password"),
                "OPENAI_API_KEY": ecs.Secret.from_secrets_manager(openai_secret, "OPENAI_API_KEY"),
            },
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix=f"factchecker-{service_name}",
            ),
        )

        # Create service
        service = ecs.FargateService(
            self,
            f"{service_id}Service",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=1,
        )

        # Auto-scaling based on queue depth
        # CloudWatch metrics disabled - scaling removed
        # scalable_target = service.auto_scale_task_count(
        #     min_capacity=1,
        #     max_capacity=10,
        # )
        #
        # # Note: Queue depth metric would need to be set up separately
        # # This is a placeholder for queue-based scaling
        # # Extract queue name from URL for CloudWatch metric dimension
        # queue_name = queue_url.split("/")[-1]
        # scalable_target.scale_on_metric(
        #     f"{service_id}QueueScaling",
        #     metric=cloudwatch.Metric(
        #         namespace="AWS/SQS",
        #         metric_name="ApproximateNumberOfMessagesVisible",
        #         dimensions_map={"QueueName": queue_name},
        #     ),
        #     scaling_steps=[
        #         appscaling.ScalingInterval(upper=0, change=0),
        #         appscaling.ScalingInterval(lower=1, change=+1),
        #         appscaling.ScalingInterval(lower=10, change=+2),
        #     ],
        # )

    def _create_lambda_worker(
        self,
        worker_id: str,
        service_name: str,
        vpc: ec2.IVpc,
        database_secret: secretsmanager.ISecret,
        openai_secret: secretsmanager.ISecret,
        environment: dict,
        queue: sqs.IQueue,
        queue_arn: str,
        memory: int,
        repository: ecr.IRepository,
    ):
        """Create a Lambda worker function triggered by SQS."""
        # Create Lambda execution role
        lambda_role = iam.Role(
            self,
            f"{worker_id}LambdaRole",
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

        # Grant SQS permissions (for receiving messages via event source mapping)
        # Note: Lambda event source mapping handles receive/delete automatically
        # But we still need permissions for the queue
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                ],
                resources=[queue_arn],
            )
        )

        # Grant S3 permissions
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                resources=["*"],  # Restrict to specific buckets in production
            )
        )

        # Grant SQS send permissions (for next queue in pipeline)
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["sqs:SendMessage"],
                resources=["*"],  # Restrict to specific queues in production
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
        # Note: OpenAI secret uses from_secret_name_v2 which returns partial ARN without suffix
        # AWS Secrets Manager adds a random 6-character suffix, so we need wildcard for OpenAI secret
        openai_secret_arn_pattern = f"{openai_secret.secret_arn}-*"
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["secretsmanager:GetSecretValue"],
                resources=[database_secret.secret_arn, openai_secret_arn_pattern],
            )
        )

        # Add database connection info to environment
        env = {
            **environment,
            "DB_HOST": self.database_endpoint,
            "DB_PORT": "5432",
            "DB_NAME": "factchecker",
        }

        # Get private subnets for VPC configuration
        private_subnets = vpc.private_subnets

        # Create security group for Lambda
        lambda_sg = ec2.SecurityGroup(
            self,
            f"{worker_id}LambdaSecurityGroup",
            vpc=vpc,
            description=f"Security group for {worker_id} Lambda",
            allow_all_outbound=True,
        )
        
        # Note: Database already allows access from VPC (see DatabaseStack)
        # No need to explicitly allow Lambda security group to avoid cyclic dependency

        # Create Lambda function using container image
        lambda_function = lambda_.DockerImageFunction(
            self,
            f"{worker_id}Lambda",
            code=lambda_.DockerImageCode.from_ecr(
                repository=repository,
                tag_or_digest="latest",
            ),
            function_name=f"factchecker-{service_name}",
            role=lambda_role,
            timeout=Duration.minutes(15),  # Max Lambda timeout
            memory_size=memory,
            environment=env,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=private_subnets),
            security_groups=[lambda_sg],
        )

        # Add secrets as environment variables (Lambda doesn't support secrets directly like ECS)
        # We'll need to fetch them at runtime, but we can pass the ARNs
        lambda_function.add_environment("DB_SECRET_ARN", database_secret.secret_arn)
        lambda_function.add_environment("OPENAI_SECRET_ARN", openai_secret.secret_arn)

        # Configure SQS event source mapping
        lambda_function.add_event_source(
            lambda_event_sources.SqsEventSource(
                queue=queue,
                batch_size=10,  # Process up to 10 messages per invocation
                max_batching_window=Duration.seconds(0),  # Process immediately
                report_batch_item_failures=True,  # Enable partial batch processing
            )
        )

