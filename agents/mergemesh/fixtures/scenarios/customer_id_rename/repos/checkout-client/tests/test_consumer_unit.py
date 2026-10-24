"""Isolated unit tests for checkout-client (PR #89) using a stale mock."""

from __future__ import annotations

import sys
from pathlib import Path

CONSUMER_DIR = Path(__file__).resolve().parent.parent
if str(CONSUMER_DIR) not in sys.path:
    sys.path.insert(0, str(CONSUMER_DIR))

from client import build_checkout_session, get_customer_id  # noqa: E402


def test_consumer_with_stale_mocked_provider_payload() -> None:
    """Passes in isolation because the mock still uses old key 'customer_id'."""
    stale_mock_payload = {
        "customer_id": "cus_123",
        "status": "active",
    }
    assert get_customer_id(stale_mock_payload) == "cus_123"
    session = build_checkout_session(stale_mock_payload)
    assert session["session_customer"] == "cus_123"
    assert session["ready"] is True
    assert session["client_version"] == "2.4.1"
