"""REST API EC2 service stack."""
from aws_cdk import (
    Stack,
    CfnOutput,
    Fn,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    aws_ecr as ecr,
    aws_apigateway as apigw,
    Duration,
)
from constructs import Construct


class ApiStack(Stack):
    """Stack for REST API EC2 service."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        database_secret: secretsmanager.ISecret,
        database_endpoint: str,
        video_bucket_name: str,
        assets_bucket_name: str,
        url_to_video_queue_url: str,
        api_repository: ecr.IRepository,
        sns_platform_application_arn: str = None,
        sns_platform_application_arn_sandbox: str = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get OpenAI secret
        openai_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "OpenAISecret", "factchecker/openai-api-key"
        )

        # Create instance role with permissions
        instance_role = iam.Role(
            self,
            "ApiInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEC2ContainerRegistryReadOnly"
                ),
            ],
        )

        # Grant SQS permissions
        instance_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["sqs:SendMessage"],
                resources=[f"arn:aws:sqs:{self.region}:{self.account}:factchecker-url-to-video"],
            )
        )

        # Grant Secrets Manager permissions
        # Note: openai_secret uses from_secret_name_v2 which returns partial ARN without suffix
        instance_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["secretsmanager:GetSecretValue"],
                resources=[database_secret.secret_arn, f"{openai_secret.secret_arn}-*"],
            )
        )

        # Grant S3 permissions for generating presigned URLs
        instance_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:PutObject"],
                resources=[
                    f"arn:aws:s3:::{assets_bucket_name}/*",
                    f"arn:aws:s3:::{video_bucket_name}/*",
                ],
            )
        )

        # Grant SNS permissions for push notification device registration
        sns_arns = [a for a in (sns_platform_application_arn, sns_platform_application_arn_sandbox) if a]
        if sns_arns:
            instance_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["sns:CreatePlatformEndpoint"],
                    resources=sns_arns,
                )
            )

        # Grant CloudWatch Logs permissions (for Docker awslogs driver)
        instance_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                resources=["arn:aws:logs:*:*:*"],
            )
        )

        # Create API Gateway REST API (needed for environment variables)
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
                throttling_rate_limit=50,
                throttling_burst_limit=100,
                stage_name="prod",
                metrics_enabled=False,
            ),
        )

        # Create "basic-user" usage plan for Apple Sign In users
        basic_user_usage_plan = self.rest_api.add_usage_plan(
            "BasicUserUsagePlan",
            name="basic-user",
            throttle=apigw.ThrottleSettings(
                rate_limit=50,
                burst_limit=100,
            ),
            quota=apigw.QuotaSettings(
                limit=10000,
                period=apigw.Period.DAY,
            ),
        )

        basic_user_usage_plan.add_api_stage(
            stage=self.rest_api.deployment_stage,
        )

        # Grant API Gateway permissions for creating API keys and associating with usage plans
        instance_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "apigateway:POST",
                    "apigateway:GET",
                    "apigateway:PUT",
                    "apigateway:PATCH",
                ],
                resources=[
                    f"arn:aws:apigateway:{self.region}::/apikeys",
                    f"arn:aws:apigateway:{self.region}::/apikeys/*",
                    f"arn:aws:apigateway:{self.region}::/usageplans",
                    f"arn:aws:apigateway:{self.region}::/usageplans/*",
                    f"arn:aws:apigateway:{self.region}::/usageplans/*/keys",
                    f"arn:aws:apigateway:{self.region}::/usageplans/*/keys/*",
                ],
            )
        )

        # Create security group for EC2 instance
        api_sg = ec2.SecurityGroup(
            self,
            "ApiSecurityGroup",
            vpc=vpc,
            description="Security group for API EC2 instance",
            allow_all_outbound=True,
        )
        api_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(8000),
            "Allow API Gateway HTTP integration",
        )

        # Build UserData script
        user_data = ec2.UserData.for_linux()

        # Build SNS env var flags for docker run
        sns_env_flags = ""
        if sns_platform_application_arn:
            sns_env_flags += f" -e SNS_PLATFORM_APPLICATION_ARN={sns_platform_application_arn}"
        if sns_platform_application_arn_sandbox:
            sns_env_flags += f" -e SNS_PLATFORM_APPLICATION_ARN_SANDBOX={sns_platform_application_arn_sandbox}"

        # Write helper script to safely extract secrets into a Docker env file
        write_env_script = (
            "import json\n"
            "db = json.load(open('/tmp/db_creds.json'))\n"
            "openai_creds = json.load(open('/tmp/openai_creds.json'))\n"
            "with open('/tmp/secrets.env', 'w') as f:\n"
            "    f.write('DB_USER=' + db['username'] + '\\n')\n"
            "    f.write('DB_PASSWORD=' + db['password'] + '\\n')\n"
            "    f.write('OPENAI_API_KEY=' + openai_creds['OPENAI_API_KEY'] + '\\n')\n"
        )
        user_data.add_commands(
            f"cat > /tmp/write_env.py << 'PYEOF'\n{write_env_script}PYEOF",
            "set -ex",
            # Install Docker
            "dnf install -y docker",
            "systemctl enable docker",
            "systemctl start docker",
            # ECR login
            f"aws ecr get-login-password --region {self.region} | docker login --username AWS --password-stdin {self.account}.dkr.ecr.{self.region}.amazonaws.com",
            # Fetch secrets and write Docker env file (avoids shell escaping issues with special chars in passwords)
            f"aws secretsmanager get-secret-value --secret-id '{database_secret.secret_arn}' --region {self.region} --query SecretString --output text > /tmp/db_creds.json",
            f"aws secretsmanager get-secret-value --secret-id 'factchecker/openai-api-key' --region {self.region} --query SecretString --output text > /tmp/openai_creds.json",
            "python3 /tmp/write_env.py",
            "rm -f /tmp/db_creds.json /tmp/openai_creds.json /tmp/write_env.py",
            # Pull and run the container
            f"ECR_IMAGE={api_repository.repository_uri}:latest",
            "docker pull $ECR_IMAGE",
            "docker run -d --name factchecker-api --restart=always"
            " -p 8000:8000"
            f" --log-driver=awslogs --log-opt awslogs-region={self.region} --log-opt awslogs-group=/factchecker/api --log-opt awslogs-create-group=true"
            f" -e DB_HOST={database_endpoint}"
            " -e DB_PORT=5432"
            " -e DB_NAME=factchecker"
            f" -e VIDEO_BUCKET={video_bucket_name}"
            f" -e ASSETS_BUCKET={assets_bucket_name}"
            f" -e URL_TO_VIDEO_QUEUE_URL={url_to_video_queue_url}"
            f" -e AWS_REGION={self.region}"
            f" -e API_GATEWAY_REST_API_ID={self.rest_api.rest_api_id}"
            f" -e API_GATEWAY_USAGE_PLAN_ID={basic_user_usage_plan.usage_plan_id}"
            " -e APPLE_CLIENT_ID=HarkiBains.FactCheck"
            f"{sns_env_flags}"
            " --env-file /tmp/secrets.env"
            " $ECR_IMAGE",
            "rm -f /tmp/secrets.env",
        )

        # Create EC2 instance
        self.instance = ec2.Instance(
            self,
            "ApiInstance",
            instance_type=ec2.InstanceType("t3.small"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=api_sg,
            role=instance_role,
            user_data=user_data,
            user_data_causes_replacement=True,
        )

        # Attach Elastic IP for stable addressing
        eip = ec2.CfnEIP(self, "ApiElasticIp")
        ec2.CfnEIPAssociation(
            self,
            "ApiEipAssociation",
            allocation_id=eip.attr_allocation_id,
            instance_id=self.instance.instance_id,
        )

        # Create API key for authentication
        api_key = self.rest_api.add_api_key(
            "ApiKey",
            description="FactChecker API Key",
        )

        # Create HTTP proxy integrations using Elastic IP
        api_base_url = Fn.join("", ["http://", eip.attr_public_ip, ":8000"])

        # /auth/apple-signin endpoint (public, no API key)
        auth_resource = self.rest_api.root.add_resource("auth")
        apple_signin_resource = auth_resource.add_resource("apple-signin")
        apple_signin_resource.add_method(
            "POST",
            apigw.HttpIntegration(
                Fn.join("", ["http://", eip.attr_public_ip, ":8000/auth/apple-signin"]),
                http_method="POST",
                proxy=True,
            ),
            api_key_required=False,
        )

        # Catch-all proxy resource
        proxy_integration = apigw.HttpIntegration(
            Fn.join("", ["http://", eip.attr_public_ip, ":8000/{proxy}"]),
            http_method="ANY",
            proxy=True,
            options=apigw.IntegrationOptions(
                request_parameters={
                    "integration.request.path.proxy": "method.request.path.proxy",
                },
            ),
        )

        proxy_resource = self.rest_api.root.add_resource("{proxy+}")
        proxy_resource.add_method(
            "ANY",
            proxy_integration,
            api_key_required=True,
            request_parameters={
                "method.request.path.proxy": True,
            },
        )

        # Root resource
        self.rest_api.root.add_method(
            "ANY",
            apigw.HttpIntegration(
                Fn.join("", ["http://", eip.attr_public_ip, ":8000"]),
                http_method="ANY",
                proxy=True,
            ),
            api_key_required=True,
        )

        # Create usage plan with throttling
        usage_plan = self.rest_api.add_usage_plan(
            "UsagePlan",
            name="factchecker-usage-plan",
            throttle=apigw.ThrottleSettings(
                rate_limit=50,
                burst_limit=100,
            ),
            quota=apigw.QuotaSettings(
                limit=10000,
                period=apigw.Period.DAY,
            ),
        )

        usage_plan.add_api_key(api_key)
        usage_plan.add_api_stage(
            stage=self.rest_api.deployment_stage,
        )

        # Outputs
        CfnOutput(
            self,
            "ApiEndpoint",
            value=self.rest_api.url,
            description="API Gateway endpoint URL",
        )

        CfnOutput(
            self,
            "Ec2PublicIp",
            value=eip.attr_public_ip,
            description="EC2 Elastic IP (direct access on port 8000)",
        )

        CfnOutput(
            self,
            "ApiKeyId",
            value=api_key.key_id,
            description="API Key ID - use AWS CLI to get the key value: aws apigateway get-api-key --api-key <key-id> --include-value",
        )

        CfnOutput(
            self,
            "ApiHealthCheck",
            value=f"{self.rest_api.url}health",
            description="API health check endpoint via API Gateway",
        )
