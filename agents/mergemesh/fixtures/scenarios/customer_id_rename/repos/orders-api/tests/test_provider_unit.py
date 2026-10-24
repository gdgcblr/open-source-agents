"""Isolated unit tests for orders-api (PR #142)."""

from __future__ import annotations

import sys
from pathlib import Path

PROVIDER_DIR = Path(__file__).resolve().parent.parent
if str(PROVIDER_DIR) not in sys.path:
    sys.path.insert(0, str(PROVIDER_DIR))

from provider import get_customer_response  # noqa: E402


def test_provider_returns_active_customer_camelcase() -> None:
    """Isolated provider test validates the new camelCase contract (`customerId`)."""
    payload = get_customer_response("cus_123")
    assert payload["customerId"] == "cus_123"
    assert payload["status"] == "active"
    assert "customer_id" not in payload
