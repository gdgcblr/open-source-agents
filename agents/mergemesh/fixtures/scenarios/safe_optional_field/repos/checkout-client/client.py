"""Consumer client for checkout-client (PR #92)."""


def get_customer_id(payload: dict) -> str:
    """Extract customer identifier from orders-api response payload."""
    return payload["customer_id"]


def build_checkout_session(payload: dict) -> dict:
    """Build checkout session from orders-api customer response."""
    cid = get_customer_id(payload)
    label = payload.get("display_name", "Guest")
    return {
        "session_customer": cid,
        "ready": payload.get("status") == "active",
        "display_name": label,
    }
