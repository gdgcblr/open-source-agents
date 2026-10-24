"""Combined cross-repository integration test: orders-api (PR #142) + checkout-client (PR #89)."""

from __future__ import annotations

import sys
from pathlib import Path

REPOS_DIR = Path(__file__).resolve().parent.parent.parent
PROVIDER_DIR = REPOS_DIR / "orders-api"
CONSUMER_DIR = REPOS_DIR / "checkout-client"

for d in (PROVIDER_DIR, CONSUMER_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from client import build_checkout_session  # noqa: E402
from provider import get_customer_response  # noqa: E402


def test_combined_orders_api_to_checkout_client_contract() -> None:
    """Executes checkout-client against the real candidate payload from orders-api.

    Expected outcome: FAIL with KeyError: 'customer_id' because orders-api now returns 'customerId'.
    """
    live_provider_payload = get_customer_response("cus_123")
    session = build_checkout_session(live_provider_payload)
    assert session["session_customer"] == "cus_123"
    assert session["ready"] is True
