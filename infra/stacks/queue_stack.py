"""SQS queues stack."""
from aws_cdk import (
    Stack,
    aws_sqs as sqs,
    Duration,
)
from constructs import Construct


class QueueStack(Stack):
    """Stack for SQS queues."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Dead-letter queue for failed messages
        dlq = sqs.Queue(
            self,
            "DeadLetterQueue",
            queue_name="factchecker-dlq",
            retention_period=Duration.days(14),
        )

        # Queue: URL to Video
        self.url_to_video_queue = sqs.Queue(
            self,
            "UrlToVideoQueue",
            queue_name="factchecker-url-to-video",
            visibility_timeout=Duration.minutes(15),
            retention_period=Duration.days(14),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=dlq,
            ),
        )

        # Queue: Video to Transcript
        self.video_to_transcript_queue = sqs.Queue(
            self,
            "VideoToTranscriptQueue",
            queue_name="factchecker-video-to-transcript",
            visibility_timeout=Duration.minutes(30),
            retention_period=Duration.days(14),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=dlq,
            ),
        )

        # Queue: Transcript to Claims
        self.transcript_to_claims_queue = sqs.Queue(
            self,
            "TranscriptToClaimsQueue",
            queue_name="factchecker-transcript-to-claims",
            visibility_timeout=Duration.minutes(10),
            retention_period=Duration.days(14),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=dlq,
            ),
        )

        # Queue: Claims to Verified
        self.claims_to_verified_queue = sqs.Queue(
            self,
            "ClaimsToVerifiedQueue",
            queue_name="factchecker-claims-to-verified",
            visibility_timeout=Duration.minutes(10),
            retention_period=Duration.days(14),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=dlq,
            ),
        )

