"""Common Lambda handler plumbing."""
import json
import asyncio
from typing import Dict, Any, List, Callable, Optional

from shared.secrets import initialize_secrets
from shared.database import get_sessionmaker


def sync_handler(async_handler_fn, logger):
    """Create a synchronous Lambda handler that wraps an async handler.

    Lambda Runtime Interface Client requires a synchronous handler.
    """
    def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        try:
            loop = asyncio.get_event_loop()
            logger.info("Using existing event loop")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            logger.info("Created new event loop")
        return loop.run_until_complete(async_handler_fn(event, context))
    return handler


def sqs_batch_handler(
    process_message_fn: Callable,
    logger,
    setup_fn: Optional[Callable] = None,
):
    """Create an async SQS batch handler.

    Args:
        process_message_fn: async function(message_body, session, **setup_kwargs) -> bool
        logger: structlog logger
        setup_fn: optional function() -> dict of kwargs to pass to process_message_fn.
                  Called once after secrets init; use for env var validation.

    Returns:
        An async handler function for Lambda.
    """
    async def async_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        await initialize_secrets()

        setup_kwargs = setup_fn() if setup_fn else {}

        batch_item_failures: List[Dict[str, str]] = []

        for record in event.get("Records", []):
            message_id = record.get("messageId", "")

            try:
                message_body = json.loads(record.get("body", "{}"))

                async with get_sessionmaker()() as session:
                    success = await process_message_fn(message_body, session, **setup_kwargs)

                    if not success:
                        batch_item_failures.append({"itemIdentifier": message_id})
                        logger.warning("Failed to process message", message_id=message_id)
                    else:
                        logger.info("Successfully processed message", message_id=message_id)

            except json.JSONDecodeError as e:
                logger.error("Error decoding message", exc_info=True, error=str(e), message_id=message_id)
                batch_item_failures.append({"itemIdentifier": message_id})
            except Exception as e:
                logger.error("Error processing message", exc_info=True, error=str(e), message_id=message_id)
                batch_item_failures.append({"itemIdentifier": message_id})

        return {"batchItemFailures": batch_item_failures}

    return async_handler
