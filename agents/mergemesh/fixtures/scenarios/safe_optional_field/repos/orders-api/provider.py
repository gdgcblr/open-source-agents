"""Mock orders-api provider service for safe_optional_field (PR #148)."""

from __future__ import annotations

try:
    from fastapi import FastAPI
except ImportError:
    FastAPI = None  # type: ignore[assignment]


def get_customer_response(customer_id: str = "cus_123") -> dict[str, str]:
    """Return customer status payload with backward-compatible display_name field."""
    return {
        "customer_id": customer_id,
        "status": "active",
        "display_name": "Aditi Sharma",
    }


if FastAPI is not None:
    app = FastAPI(title="orders-api", version="1.5.0")

    @app.get("/orders/{order_id}/customer")
    def read_order_customer(order_id: str) -> dict[str, str]:
        return get_customer_response("cus_123")
