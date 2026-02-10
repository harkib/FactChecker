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
    aws_apigateway as apigw,
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
        
        # Grant S3 permissions for generating presigned URLs
        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:PutObject"],
                resources=[
                    f"arn:aws:s3:::{assets_bucket_name}/*",
                    f"arn:aws:s3:::{video_bucket_name}/*",
                ],
            )
        )
        
        # Note: API Gateway permissions will be added after rest_api is created
        # This is a placeholder - actual permissions added below after rest_api creation

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

        # Create API Gateway REST API first (needed for environment variables)
        # REST API supports throttling, API keys, and usage plans out of the box
        self.rest_api = apigw.RestApi(
            self,
            "ApiGateway",
            description="FactChecker API Gateway",
            rest_api_name="factchecker-api",
            endpoint_configuration=apigw.EndpointConfiguration(
                types=[apigw.EndpointType.REGIONAL]
            ),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["*"],
                max_age=Duration.days(1),
            ),
            deploy_options=apigw.StageOptions(
                # Configure throttling: 50 requests/second, burst of 100
                throttling_rate_limit=50,
                throttling_burst_limit=100,
                stage_name="prod",
                metrics_enabled=False,  # CloudWatch metrics disabled
            ),
        )

        # Create "basic-user" usage plan for Apple Sign In users (needed for environment variables)
        basic_user_usage_plan = self.rest_api.add_usage_plan(
            "BasicUserUsagePlan",
            name="basic-user",
            throttle=apigw.ThrottleSettings(
                rate_limit=50,  # requests per second
                burst_limit=100,  # burst capacity
            ),
            quota=apigw.QuotaSettings(
                limit=10000,  # requests per day
                period=apigw.Period.DAY,
            ),
        )
        
        # Associate basic-user usage plan with stage
        basic_user_usage_plan.add_api_stage(
            stage=self.rest_api.deployment_stage,
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
                    "API_GATEWAY_REST_API_ID": self.rest_api.rest_api_id,
                    "API_GATEWAY_USAGE_PLAN_ID": basic_user_usage_plan.usage_plan_id,
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
        
        # Configure CloudWatch logging for the API service container
        # ApplicationLoadBalancedFargateService creates a default container that we can access
        # The container's logging property can be set directly
        container = self.fargate_service.task_definition.default_container
        container.logging = ecs.LogDrivers.aws_logs(
            stream_prefix="factchecker-api",
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
        # CloudWatch metrics disabled - CPU-based scaling removed (uses CloudWatch metrics)
        # scalable_target = self.fargate_service.service.auto_scale_task_count(
        #     min_capacity=1, max_capacity=10
        # )
        # scalable_target.scale_on_cpu_utilization(
        #     "CpuScaling",
        #     target_utilization_percent=70,
        # )

        # Create API key for authentication (create before methods so we can reference it)
        api_key = self.rest_api.add_api_key(
            "ApiKey",
            description="FactChecker API Key",
        )

        # Create HTTP proxy integration with ALB
        # For REST API HTTP proxy, the URI should include {proxy} placeholder
        # The double braces {{proxy}} become {proxy} in the final string
        alb_base_url = f"http://{self.fargate_service.load_balancer.load_balancer_dns_name}"
        
        # IMPORTANT: Add /auth/apple-signin endpoint BEFORE the catch-all proxy
        # API Gateway evaluates routes in order, so specific routes must come first
        auth_resource = self.rest_api.root.add_resource("auth")
        apple_signin_resource = auth_resource.add_resource("apple-signin")
        apple_signin_resource.add_method(
            "POST",
            apigw.HttpIntegration(
                f"{alb_base_url}/auth/apple-signin",
                http_method="POST",
                proxy=True,
            ),
            api_key_required=False,  # Public endpoint - no API key required
        )
        
        proxy_integration = apigw.HttpIntegration(
            f"{alb_base_url}/{{proxy}}",
            http_method="ANY",
            proxy=True,
            options=apigw.IntegrationOptions(
                request_parameters={
                    "integration.request.path.proxy": "method.request.path.proxy",
                },
            ),
        )
        
        # Add catch-all proxy resource to forward all requests to ALB
        # This must come AFTER specific routes like /auth/apple-signin
        proxy_resource = self.rest_api.root.add_resource("{proxy+}")
        proxy_resource.add_method(
            "ANY",
            proxy_integration,
            api_key_required=True,  # Require API key for all requests
            request_parameters={
                "method.request.path.proxy": True,
            },
        )

        # Also add root resource to handle requests without path
        self.rest_api.root.add_method(
            "ANY",
            apigw.HttpIntegration(
                f"http://{self.fargate_service.load_balancer.load_balancer_dns_name}",
                http_method="ANY",
                proxy=True,
            ),
            api_key_required=True,  # Require API key for all requests
        )

        # Create usage plan with throttling (for existing hardcoded key)
        usage_plan = self.rest_api.add_usage_plan(
            "UsagePlan",
            name="factchecker-usage-plan",
            throttle=apigw.ThrottleSettings(
                rate_limit=50,  # requests per second
                burst_limit=100,  # burst capacity
            ),
            quota=apigw.QuotaSettings(
                limit=10000,  # requests per day
                period=apigw.Period.DAY,
            ),
        )

        # Associate API key with usage plan and stage
        usage_plan.add_api_key(api_key)
        usage_plan.add_api_stage(
            stage=self.rest_api.deployment_stage,
        )
        
        # Grant API Gateway permissions for creating API keys and associating with usage plans
        # These permissions are added here after rest_api is created so we can reference it
        # Note: API Gateway API keys are account-level resources (double colon ::)
        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "apigateway:POST",  # Create API key
                    "apigateway:GET",   # Get API key
                    "apigateway:PUT",   # Update API key
                    "apigateway:PATCH", # Patch API key
                ],
                resources=[
                    # Base resource for creating API keys (required for POST)
                    f"arn:aws:apigateway:{self.region}::/apikeys",
                    # Specific API key resources
                    f"arn:aws:apigateway:{self.region}::/apikeys/*",
                    # Usage plan resources
                    f"arn:aws:apigateway:{self.region}::/usageplans",
                    f"arn:aws:apigateway:{self.region}::/usageplans/*",
                    # Usage plan key associations
                    f"arn:aws:apigateway:{self.region}::/usageplans/*/keys",
                    f"arn:aws:apigateway:{self.region}::/usageplans/*/keys/*",
                ],
            )
        )

        # Output the API Gateway endpoint (primary endpoint)
        CfnOutput(
            self,
            "ApiEndpoint",
            value=self.rest_api.url,
            description="API Gateway endpoint URL (use this as your public API endpoint)",
        )

        # Output the ALB endpoint (for direct access/debugging - can be removed in production)
        CfnOutput(
            self,
            "AlbEndpoint",
            value=f"http://{self.fargate_service.load_balancer.load_balancer_dns_name}",
            description="ALB endpoint URL (direct access, behind API Gateway)",
        )

        # Output API key ID (users will need to get the key value from AWS Console or CLI)
        CfnOutput(
            self,
            "ApiKeyId",
            value=api_key.key_id,
            description="API Key ID - use AWS CLI or Console to get the key value: aws apigateway get-api-key --api-key <key-id> --include-value",
        )

        CfnOutput(
            self,
            "ApiHealthCheck",
            value=f"{self.rest_api.url}health",
            description="API health check endpoint via API Gateway",
        )

