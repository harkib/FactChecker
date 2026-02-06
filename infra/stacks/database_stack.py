"""RDS PostgreSQL database stack."""
from aws_cdk import (
    Stack,
    aws_rds as rds,
    aws_ec2 as ec2,
    aws_secretsmanager as secretsmanager,
    RemovalPolicy,
)
from constructs import Construct


class DatabaseStack(Stack):
    """Stack for RDS PostgreSQL database."""

    def __init__(self, scope: Construct, construct_id: str, vpc: ec2.IVpc, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create database credentials secret
        db_secret = secretsmanager.Secret(
            self,
            "DatabaseSecret",
            description="RDS PostgreSQL database credentials",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username":"postgres"}',
                generate_string_key="password",
                exclude_characters='"@/\\',
            ),
        )

        # Create database subnet group
        subnet_group = rds.SubnetGroup(
            self,
            "DatabaseSubnetGroup",
            vpc=vpc,
            description="Subnet group for RDS database",
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
        )

        # Create RDS PostgreSQL instance
        # Using string version to support latest AWS versions not yet in CDK enum
        # Update the version strings below to match the latest version AWS supports
        # Format: PostgresEngineVersion.of("full_version", "major_version")
        # Example: PostgresEngineVersion.of("16.1", "16") for PostgreSQL 16.1
        self.database = rds.DatabaseInstance(
            self,
            "FactCheckerDatabase",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.of("16.10", "16")
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.MICRO
            ),
            vpc=vpc,
            subnet_group=subnet_group,
            credentials=rds.Credentials.from_secret(db_secret),
            database_name="factchecker",
            removal_policy=RemovalPolicy.DESTROY,  # Change for production
            deletion_protection=False,  # Enable for production
            publicly_accessible=False,
        )

        # Create security group rule to allow access from VPC resources only
        # Restrict to VPC CIDR for defense in depth (database is already in private subnet)
        self.database.connections.allow_default_port_from(
            ec2.Peer.ipv4(vpc.vpc_cidr_block),
            description="Allow access from VPC resources (ECS tasks, Lambda functions)"
        )

        # Add host to secret after database is created
        # Note: In production, you may want to use a custom resource to update the secret
        # For now, the host will be available via the database instance endpoint
        
        self.db_secret = db_secret
        self.db_endpoint = self.database.instance_endpoint
        self.db_name = "factchecker"
        
        # Store endpoint hostname in secret (requires custom resource in production)
        # For now, services will need to construct host from endpoint

