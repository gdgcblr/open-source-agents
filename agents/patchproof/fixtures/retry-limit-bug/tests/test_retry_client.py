"""Existing unit tests in the retry-limit-bug fixture (missing boundary exhaustion assertion)."""

import pytest
from src.retry_client import FatalClientError, TransientError, retry_request


def test_succeeds_after_single_transient_failure() -> None:
    calls = 0

    def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise TransientError("temporary glitch")
        return "ok"

    assert retry_request(flaky, max_retries=3) == "ok"


def test_negative_max_retries_raises_value_error() -> None:
    with pytest.raises(ValueError):
        retry_request(lambda: "ok", max_retries=-1)


def test_fatal_client_error_not_retried() -> None:
    calls = 0

    def fatal() -> str:
        nonlocal calls
        calls += 1
        raise FatalClientError("bad auth")

    with pytest.raises(FatalClientError):
        retry_request(fatal, max_retries=3)
    assert calls == 1

