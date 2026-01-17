"""CDK app entry point."""
import aws_cdk as cdk
from stacks.vpc_stack import VpcStack
from stacks.ecr_stack import EcrStack
from stacks.database_stack import DatabaseStack
from stacks.storage_stack import StorageStack
from stacks.queue_stack import QueueStack
from stacks.api_stack import ApiStack
from stacks.worker_stacks import WorkerStacks


app = cdk.App()

# Create VPC and ECS Cluster stack
vpc_stack = VpcStack(app, "VpcStack")
vpc = vpc_stack.vpc
cluster = vpc_stack.cluster

# Create ECR stack (must be created before ECS services)
ecr_stack = EcrStack(app, "EcrStack")

# Create storage stack
storage_stack = StorageStack(app, "StorageStack")
video_bucket_name = storage_stack.video_bucket.bucket_name
assets_bucket_name = storage_stack.assets_bucket.bucket_name

# Create database stack
database_stack = DatabaseStack(app, "DatabaseStack", vpc=vpc)
db_secret = database_stack.db_secret

# Create queue stack
queue_stack = QueueStack(app, "QueueStack")
url_to_video_queue_url = queue_stack.url_to_video_queue.queue_url
video_to_transcript_queue_url = queue_stack.video_to_transcript_queue.queue_url
transcript_to_claims_queue_url = queue_stack.transcript_to_claims_queue.queue_url
claims_to_verified_queue_url = queue_stack.claims_to_verified_queue.queue_url

# Create API stack
api_stack = ApiStack(
    app,
    "ApiStack",
    vpc=vpc,
    cluster=cluster,
    database_secret=db_secret,
    database_endpoint=database_stack.db_endpoint.hostname,
    video_bucket_name=video_bucket_name,
    assets_bucket_name=assets_bucket_name,
    url_to_video_queue_url=url_to_video_queue_url,
    api_repository=ecr_stack.api_repo,
)

# Create worker stacks
worker_stacks = WorkerStacks(
    app,
    "WorkerStacks",
    vpc=vpc,
    cluster=cluster,
    database_secret=db_secret,
    database_endpoint=database_stack.db_endpoint.hostname,
    database_instance=database_stack.database,
    video_bucket_name=video_bucket_name,
    assets_bucket_name=assets_bucket_name,
    url_to_video_queue=queue_stack.url_to_video_queue,
    url_to_video_queue_url=url_to_video_queue_url,
    video_to_transcript_queue=queue_stack.video_to_transcript_queue,
    video_to_transcript_queue_url=video_to_transcript_queue_url,
    transcript_to_claims_queue=queue_stack.transcript_to_claims_queue,
    transcript_to_claims_queue_url=transcript_to_claims_queue_url,
    claims_to_verified_queue=queue_stack.claims_to_verified_queue,
    claims_to_verified_queue_url=claims_to_verified_queue_url,
    url_to_video_queue_arn=queue_stack.url_to_video_queue.queue_arn,
    video_to_transcript_queue_arn=queue_stack.video_to_transcript_queue.queue_arn,
    transcript_to_claims_queue_arn=queue_stack.transcript_to_claims_queue.queue_arn,
    claims_to_verified_queue_arn=queue_stack.claims_to_verified_queue.queue_arn,
    ecr_repositories=ecr_stack.repositories,
)

app.synth()

