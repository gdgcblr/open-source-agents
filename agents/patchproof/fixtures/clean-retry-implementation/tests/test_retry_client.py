"""Unit tests for the clean-retry-implementation control fixture."""

import pytest
from src.retry_client import FatalClientError, TransientError, retry_request


def test_retry_exhaustion_respects_max_retries_boundary() -> None:
    call_count = 0

    def always_fail() -> str:
        nonlocal call_count
        call_count += 1
        raise TransientError("still down")

    with pytest.raises(TransientError):
        retry_request(always_fail, max_retries=3)
    assert call_count == 4


def test_zero_max_retries_performs_single_attempt() -> None:
    call_count = 0

    def always_fail() -> str:
        nonlocal call_count
        call_count += 1
        raise TransientError("down")

    with pytest.raises(TransientError):
        retry_request(always_fail, max_retries=0)
    assert call_count == 1


def test_negative_max_retries_raises_value_error() -> None:
    with pytest.raises(ValueError):
        retry_request(lambda: "ok", max_retries=-1)


def test_fatal_client_error_not_retried() -> None:
    call_count = 0

    def fatal() -> str:
        nonlocal call_count
        call_count += 1
        raise FatalClientError("bad auth")

    with pytest.raises(FatalClientError):
        retry_request(fatal, max_retries=3)
    assert call_count == 1

