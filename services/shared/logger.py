"""Shared structured logging configuration using structlog."""
import os
import sys
import logging
import structlog
from typing import Optional


def configure_logging(log_level: Optional[str] = None) -> None:
    """
    Configure structlog for JSON output with timestamp and resource name.
    
    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR). If None, reads from LOG_LEVEL env var.
    """
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
    
    # Map string log level to logging constant
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    logging_level = level_map.get(log_level, logging.DEBUG)
    
    # Configure standard logging to output to stdout (for CloudWatch)
    # Use format="%(message)s" so structlog's JSON output passes through unchanged
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging_level,
        force=True,  # Override any existing configuration
    )
    
    # Configure structlog processors with stdlib integration
    processors = [
        structlog.stdlib.filter_by_level,  # Filter by log level
        structlog.stdlib.add_logger_name,  # Add logger name
        structlog.stdlib.add_log_level,  # Add log level
        structlog.stdlib.PositionalArgumentsFormatter(),  # Format positional args
        structlog.processors.TimeStamper(fmt="iso"),  # ISO 8601 timestamp
        structlog.processors.StackInfoRenderer(),  # Add stack info for exceptions
        structlog.processors.format_exc_info,  # Format exceptions
        structlog.processors.UnicodeDecoder(),  # Decode unicode
        structlog.processors.JSONRenderer(),  # JSON output
    ]
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),  # Use stdlib factory for proper integration
        cache_logger_on_first_use=True,
    )
    
    # Explicitly reset the shared.logger logger to ensure it propagates correctly
    # This is needed because Alembic's fileConfig may have modified it
    shared_logger = logging.getLogger("shared.logger")
    shared_logger.handlers = []  # Remove any handlers Alembic may have added
    shared_logger.propagate = True  # Ensure it propagates to root logger
    shared_logger.setLevel(logging_level)  # Set appropriate level


def get_logger(resource: str) -> structlog.BoundLogger:
    """
    Get a logger instance with resource name bound to context.
    
    Args:
        resource: Resource name (e.g., "url-to-video worker", "api")
    
    Returns:
        Bound logger with resource name in context
    """
    return structlog.get_logger("shared.logger").bind(resource=resource)


def bind_job_id(logger: structlog.BoundLogger, job_id: str) -> structlog.BoundLogger:
    """
    Bind job_id to logger context for job-specific logging.
    
    Args:
        logger: The logger instance
        job_id: The job ID to bind
    
    Returns:
        Logger with job_id bound to context
    """
    return logger.bind(job_id=job_id)


# Initialize logging on module import
configure_logging()

