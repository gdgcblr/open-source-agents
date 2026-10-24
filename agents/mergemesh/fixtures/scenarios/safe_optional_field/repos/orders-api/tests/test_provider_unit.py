"""Isolated unit tests for orders-api (PR #148)."""

from __future__ import annotations

import sys
from pathlib import Path

PROVIDER_DIR = Path(__file__).resolve().parent.parent
if str(PROVIDER_DIR) not in sys.path:
    sys.path.insert(0, str(PROVIDER_DIR))

from provider import get_customer_response  # noqa: E402


def test_provider_returns_customer_id_and_display_name() -> None:
    payload = get_customer_response("cus_123")
    assert payload["customer_id"] == "cus_123"
    assert payload["status"] == "active"
    assert payload["display_name"] == "Aditi Sharma"
