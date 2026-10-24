"""Synthetic fixture module containing a seeded off-by-one retry limit defect."""

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
    while retries <= max_retries:
        try:
            return operation()
        except FatalClientError:
            raise
        except TransientError:
            retries += 1

    # Seeded bug: after the while loop exits (which already ran max_retries + 1 attempts),
    # one extra retry call is performed before raising, so max_retries + 1 retries occur.
    return operation()
