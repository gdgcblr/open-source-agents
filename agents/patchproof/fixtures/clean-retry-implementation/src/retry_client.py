"""Clean control fixture module implementing bounded retries accurately."""

from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class TransientError(RuntimeError):
    """Retryable transient failure."""


class FatalClientError(RuntimeError):
    """Non-retryable permanent failure."""


def retry_request(operation: Callable[[], T], max_retries: int = 3) -> T:
    """Execute operation and retry TransientError at most max_retries times."""
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")

    retries = 0
    while retries < max_retries:
        try:
            return operation()
        except FatalClientError:
            raise
        except TransientError:
            retries += 1

    return operation()

