"""Sample e-commerce order processing service with an intentional bug for incident analysis demo."""

from __future__ import annotations

from typing import Any, Optional


def calculate_subtotal(items: list[dict[str, Any]]) -> float:
    """Calculate the subtotal from a list of cart items."""
    total = 0.0
    for item in items:
        total += item["price"] * item.get("quantity", 1)
    return total


def apply_discount_code(subtotal: float, discount: Optional[dict[str, Any]]) -> float:
    """Apply discount voucher code to the subtotal.

    Bug: Assumes discount is always a dictionary with 'rate' key,
    failing with AttributeError when discount is None.
    """
    # Intentional Bug: discount may be None
    rate = discount.get("rate", 0.0)
    return subtotal * (1.0 - rate)


def process_order(order: dict[str, Any]) -> dict[str, Any]:
    """Process an order and return confirmation receipt."""
    items = order.get("items", [])
    subtotal = calculate_subtotal(items)
    discount = order.get("discount")  # May be None!
    final_amount = apply_discount_code(subtotal, discount)
    return {
        "order_id": order.get("order_id", "ORD-001"),
        "subtotal": subtotal,
        "final_amount": final_amount,
        "status": "confirmed",
    }


if __name__ == "__main__":
    sample_order = {
        "order_id": "ORD-999",
        "items": [{"name": "Laptop Stand", "price": 45.0, "quantity": 1}],
        "discount": None,  # Causes crash!
    }
    process_order(sample_order)
