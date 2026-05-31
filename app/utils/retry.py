import functools
import asyncio
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import httpx


def async_retry(max_attempts: int = 3, wait_min: float = 1, wait_max: float = 10):
    """Decorator for retrying async functions with exponential backoff."""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
        retry=retry_if_exception_type((httpx.HTTPError, ConnectionError, TimeoutError)),
        reraise=True,
    )
