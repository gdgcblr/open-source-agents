"""Mock orders-api provider service (PR #142 candidate version)."""

from __future__ import annotations

try:
    from fastapi import FastAPI
except ImportError:
    FastAPI = None  # type: ignore[assignment]


def get_customer_response(customer_id: str = "cus_123") -> dict[str, str]:
    """Return customer status payload for downstream checkout services.

    PR #142 renamed 'customer_id' -> 'customerId'.
    """
    return {
        "customerId": customer_id,
        "status": "active",
    }


if FastAPI is not None:
    app = FastAPI(title="orders-api", version="2.0.0-rc1")

    @app.get("/orders/{order_id}/customer")
    def read_order_customer(order_id: str) -> dict[str, str]:
        return get_customer_response("cus_123")
