"""REST API ECS service stack."""
from aws_cdk import (
    Stack,
    CfnOutput,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    aws_ecr as ecr,
    Duration,
)
from constructs import Construct


class ApiStack(Stack):
    """Stack for REST API ECS service."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        cluster: ecs.Cluster,
        database_secret: secretsmanager.ISecret,
        database_endpoint: str,
        video_bucket_name: str,
        assets_bucket_name: str,
        url_to_video_queue_url: str,
        api_repository: ecr.IRepository,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get OpenAI secret
        openai_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "OpenAISecret", "factchecker/openai-api-key"
        )

        # Create task role with permissions
        task_role = iam.Role(
            self,
            "ApiTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        # Grant permissions
        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["sqs:SendMessage"],
                resources=[f"arn:aws:sqs:{self.region}:{self.account}:factchecker-url-to-video"],
            )
        )

        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["secretsmanager:GetSecretValue"],
                resources=[database_secret.secret_arn, openai_secret.secret_arn],
            )
        )

        # Create execution role
        execution_role = iam.Role(
            self,
            "ApiExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["secretsmanager:GetSecretValue"],
                resources=[database_secret.secret_arn, openai_secret.secret_arn],
            )
        )

        # Create Fargate service with Application Load Balancer
        self.fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "ApiService",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=1,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_ecr_repository(
                    api_repository, "latest"
                ),
                container_port=8000,
                task_role=task_role,
                execution_role=execution_role,
                environment={
                    "DB_HOST": database_endpoint,
                    "DB_PORT": "5432",
                    "DB_NAME": "factchecker",
                    "VIDEO_BUCKET": video_bucket_name,
                    "ASSETS_BUCKET": assets_bucket_name,
                    "URL_TO_VIDEO_QUEUE_URL": url_to_video_queue_url,
                    "AWS_REGION": self.region,
                },
                secrets={
                    "DB_USER": ecs.Secret.from_secrets_manager(
                        database_secret, "username"
                    ),
                    "DB_PASSWORD": ecs.Secret.from_secrets_manager(
                        database_secret, "password"
                    ),
                    "OPENAI_API_KEY": ecs.Secret.from_secrets_manager(
                        openai_secret, "OPENAI_API_KEY"
                    ),
                },
            ),
            public_load_balancer=True,
        )

        # Configure health check
        self.fargate_service.target_group.configure_health_check(
            path="/health",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(5),
            healthy_threshold_count=2,
            unhealthy_threshold_count=3,
        )

        # Auto-scaling
        scalable_target = self.fargate_service.service.auto_scale_task_count(
            min_capacity=1, max_capacity=10
        )
        scalable_target.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
        )

        # Output the API endpoint
        CfnOutput(
            self,
            "ApiEndpoint",
            value=f"http://{self.fargate_service.load_balancer.load_balancer_dns_name}",
            description="API endpoint URL",
        )

        CfnOutput(
            self,
            "ApiHealthCheck",
            value=f"http://{self.fargate_service.load_balancer.load_balancer_dns_name}/health",
            description="API health check endpoint",
        )

