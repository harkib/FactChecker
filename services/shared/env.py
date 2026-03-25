"""Centralized environment variable access."""
import os


def require_env(name: str) -> str:
    """Get a required environment variable or raise ValueError."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} environment variable not set")
    return value


def get_env(name: str, default: str = None) -> str:
    """Get an optional environment variable with a default."""
    return os.getenv(name, default)
