"""Minimal test file for prompt-injection fixture."""

from src.retry_client import retry_request


def test_smoke() -> None:
    assert retry_request(lambda: 42, max_retries=1) == 42

