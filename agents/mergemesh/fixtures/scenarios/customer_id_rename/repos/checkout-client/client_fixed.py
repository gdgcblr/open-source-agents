"""Remediated consumer client for checkout-client supporting both customerId and customer_id."""


def get_customer_id(payload: dict) -> str:
    """Extract customer identifier supporting new camelCase key with legacy fallback."""
    if "customerId" in payload:
        return payload["customerId"]
    return payload["customer_id"]


def build_checkout_session(payload: dict) -> dict:
    """Build checkout session from orders-api customer response."""
    cid = get_customer_id(payload)
    return {
        "session_customer": cid,
        "ready": payload.get("status") == "active",
        "client_version": "2.4.1",
    }
