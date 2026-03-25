"""CDK app entry point."""
import aws_cdk as cdk
from stacks.vpc_stack import VpcStack
from stacks.ecr_stack import EcrStack
from stacks.database_stack import DatabaseStack
from stacks.storage_stack import StorageStack
from stacks.queue_stack import QueueStack
from stacks.sns_push_stack import SnsPushStack
from stacks.api_stack import ApiStack
from stacks.worker_stacks import WorkerStacks


app = cdk.App()

# Create VPC stack
vpc_stack = VpcStack(app, "VpcStack")
vpc = vpc_stack.vpc

# Create ECR stack (must be created before ECS services)
ecr_stack = EcrStack(app, "EcrStack")

# Create database stack (needed for storage stack S3 event handler)
database_stack = DatabaseStack(app, "DatabaseStack", vpc=vpc)
db_secret = database_stack.db_secret

# Create queue stack (needed for storage stack S3 event handler)
queue_stack = QueueStack(app, "QueueStack")
video_to_transcript_queue_url = queue_stack.video_to_transcript_queue.queue_url
video_to_transcript_queue_arn = queue_stack.video_to_transcript_queue.queue_arn

# Create storage stack with S3 event handler
storage_stack = StorageStack(
    app,
    "StorageStack",
    vpc=vpc_stack.vpc,
    database_secret=database_stack.db_secret,
    database_endpoint=database_stack.db_endpoint.hostname,
    video_to_transcript_queue_url=video_to_transcript_queue_url,
    video_to_transcript_queue_arn=video_to_transcript_queue_arn,
    s3_event_repository=ecr_stack.repositories.get("s3-video-event"),
)
video_bucket_name = storage_stack.video_bucket.bucket_name
assets_bucket_name = storage_stack.assets_bucket.bucket_name

# Get remaining queue URLs
url_to_video_queue_url = queue_stack.url_to_video_queue.queue_url
transcript_to_claims_queue_url = queue_stack.transcript_to_claims_queue.queue_url

# Create SNS push stack (APNs for iOS). Requires secret factchecker/apns-credentials.
sns_push_stack = SnsPushStack(app, "SnsPushStack")
sns_platform_application_arn = sns_push_stack.platform_application_arn
sns_platform_application_arn_sandbox = sns_push_stack.platform_application_arn_sandbox

# Create API stack (depends on SNS stack for push notification ARN)
api_stack = ApiStack(
    app,
    "ApiStack",
    vpc=vpc,
    database_secret=db_secret,
    database_endpoint=database_stack.db_endpoint.hostname,
    video_bucket_name=video_bucket_name,
    assets_bucket_name=assets_bucket_name,
    url_to_video_queue_url=url_to_video_queue_url,
    api_repository=ecr_stack.api_repo,
    sns_platform_application_arn=sns_platform_application_arn,
    sns_platform_application_arn_sandbox=sns_platform_application_arn_sandbox,
)

# Create worker stacks
worker_stacks = WorkerStacks(
    app,
    "WorkerStacks",
    vpc=vpc,
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
    url_to_video_queue_arn=queue_stack.url_to_video_queue.queue_arn,
    video_to_transcript_queue_arn=queue_stack.video_to_transcript_queue.queue_arn,
    transcript_to_claims_queue_arn=queue_stack.transcript_to_claims_queue.queue_arn,
    ecr_repositories=ecr_stack.repositories,
    sns_platform_application_arn=sns_platform_application_arn,
)
api_stack.node.add_dependency(sns_push_stack)
worker_stacks.node.add_dependency(sns_push_stack)

app.synth()

