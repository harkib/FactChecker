"""VPC and ECS Cluster stack."""
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
)
from constructs import Construct


class VpcStack(Stack):
    """Stack for VPC and ECS Cluster."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create VPC
        self.vpc = ec2.Vpc(
            self,
            "FactCheckerVpc",
            max_azs=2,
            nat_gateways=1,
        )

        # Create ECS Cluster
        self.cluster = ecs.Cluster(
            self,
            "FactCheckerCluster",
            vpc=self.vpc,
            container_insights=True,
        )

