"""SNS platform application for APNs (iOS push notifications).

CloudFormation does not natively support AWS::SNS::PlatformApplication, so we use
a Lambda-backed custom resource to create/delete it.
"""
import os
from aws_cdk import (
    CustomResource,
    Stack,
    CfnOutput,
    Duration,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_secretsmanager as secretsmanager,
    custom_resources as cr,
)
from constructs import Construct


class SnsPushStack(Stack):
    """Stack for SNS platform application (APNs) for iOS push. Requires secret factchecker/apns-credentials with keys: PlatformCredential (.p8 content), PlatformPrincipal (Key ID), ApplePlatformTeamID, ApplePlatformBundleID."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        apns_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "APNsSecret", "factchecker/apns-credentials"
        )

        # IAM role for SNS to write delivery status logs to CloudWatch
        sns_feedback_role = iam.Role(
            self,
            "SnsDeliveryStatusRole",
            assumed_by=iam.ServicePrincipal("sns.amazonaws.com"),
            description="Allows SNS to write delivery status to CloudWatch Logs",
        )
        sns_feedback_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:PutLogEventsBatch",
                ],
                resources=[f"arn:aws:logs:{self.region}:{self.account}:log-group:sns/*"],
            )
        )

        # Lambda-backed custom resource (CFN doesn't support SNS PlatformApplication natively)
        handler = lambda_.Function(
            self,
            "SnsPlatformHandler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "..", "sns_platform_handler")
            ),
            timeout=Duration.seconds(60),
        )
        apns_secret.grant_read(handler)
        handler.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "sns:CreatePlatformApplication",
                    "sns:DeletePlatformApplication",
                    "sns:SetPlatformApplicationAttributes",
                ],
                resources=["*"],
            )
        )

        # Allow Lambda to pass the feedback role to SNS (required for delivery status logging)
        handler.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["iam:PassRole"],
                resources=[sns_feedback_role.role_arn],
            )
        )

        provider = cr.Provider(self, "SnsPlatformProvider", on_event_handler=handler)
        self.custom_resource = CustomResource(
            self,
            "APNsPlatformApplication",
            service_token=provider.service_token,
            properties={
                "SecretArn": apns_secret.secret_arn,
                "Name": "factchecker-ios-apns",
                "SuccessFeedbackRoleArn": sns_feedback_role.role_arn,
                "FailureFeedbackRoleArn": sns_feedback_role.role_arn,
                "SuccessFeedbackSampleRate": "100",
            },
        )

        CfnOutput(
            self,
            "SnsPlatformApplicationArn",
            value=self.custom_resource.get_att_string("PlatformApplicationArn"),
            description="SNS platform application ARN for APNs production",
        )
        CfnOutput(
            self,
            "SnsPlatformApplicationArnSandbox",
            value=self.custom_resource.get_att_string("PlatformApplicationArnSandbox"),
            description="SNS platform application ARN for APNs sandbox (Xcode debug builds)",
        )

    @property
    def platform_application_arn(self) -> str:
        return self.custom_resource.get_att_string("PlatformApplicationArn")

    @property
    def platform_application_arn_sandbox(self) -> str:
        return self.custom_resource.get_att_string("PlatformApplicationArnSandbox")
