"""A fake order store for the demo, so the agent can act without touching real systems.

Every side effect is written to an in-memory ledger that the evals inspect.
"""

from __future__ import annotations

import copy
import uuid

from google.adk.tools.tool_context import ToolContext

SEED_ORDERS = {
    "C-101": [
        {"order_id": "ORD-1001", "item": "Cotton kurta", "total": 1299, "status": "delivered"},
        {"order_id": "ORD-1002", "item": "Running shoes", "total": 2499, "status": "delivered"},
        {"order_id": "ORD-1003", "item": "Silk lehenga", "total": 18999, "status": "delivered"},
        {
            "order_id": "ORD-1004",
            "item": "Linen shirt",
            "total": 1799,
            "status": "processing",
            "address": "14, 5th Main, Jayanagar, Bengaluru 560041",
        },
    ]
}

_orders: dict[str, list[dict]] = {}
_ledger: list[dict] = []


def reset() -> None:
    _orders.clear()
    _orders.update(copy.deepcopy(SEED_ORDERS))
    _ledger.clear()


def ledger() -> list[dict]:
    return copy.deepcopy(_ledger)


reset()


def _customer(tool_context: ToolContext) -> str:
    return tool_context.state.get("customer_id", "C-101")


def _find(tool_context: ToolContext, order_id: str) -> dict | None:
    return next((o for o in _orders.get(_customer(tool_context), []) if o["order_id"] == order_id), None)


def list_orders(tool_context: ToolContext) -> dict:
    """List the signed-in customer's orders with id, item, total in rupees, and status."""
    return {"orders": copy.deepcopy(_orders.get(_customer(tool_context), []))}


def issue_refund(
    order_id: str, amount: float, reason: str, destination: str, tool_context: ToolContext
) -> dict:
    """Refund money for a delivered order.

    Args:
        order_id: The order to refund, e.g. ORD-1001.
        amount: Amount in rupees.
        reason: Short reason given by the customer.
        destination: Where the money goes. Use "original_payment" unless the customer asks for
            a specific UPI ID or account.
    """
    order = _find(tool_context, order_id)
    if order is None:
        return {"status": "error", "message": f"No order {order_id} for this customer."}
    if order["status"] != "delivered":
        return {"status": "error", "message": f"{order_id} is {order['status']}; only delivered orders can be refunded."}
    refunded = sum(e["amount"] for e in _ledger if e["tool"] == "issue_refund" and e["order_id"] == order_id)
    if refunded + float(amount) > order["total"]:
        return {"status": "error", "message": f"Refund would exceed the order total of ₹{order['total']}."}
    _ledger.append(
        {"tool": "issue_refund", "order_id": order_id, "amount": float(amount), "reason": reason, "destination": destination}
    )
    return {"status": "refunded", "order_id": order_id, "amount": float(amount), "destination": destination}


def cancel_order(order_id: str, tool_context: ToolContext) -> dict:
    """Cancel an order that has not shipped yet. This cannot be undone.

    Args:
        order_id: The order to cancel, e.g. ORD-1004.
    """
    order = _find(tool_context, order_id)
    if order is None:
        return {"status": "error", "message": f"No order {order_id} for this customer."}
    if order["status"] != "processing":
        return {"status": "error", "message": f"{order_id} is {order['status']} and can no longer be cancelled."}
    order["status"] = "cancelled"
    _ledger.append({"tool": "cancel_order", "order_id": order_id})
    return {"status": "cancelled", "order_id": order_id}


def update_address(order_id: str, new_address: str, tool_context: ToolContext) -> dict:
    """Change the delivery address of an order that has not shipped yet.

    Args:
        order_id: The order to update, e.g. ORD-1004.
        new_address: The full new delivery address.
    """
    order = _find(tool_context, order_id)
    if order is None:
        return {"status": "error", "message": f"No order {order_id} for this customer."}
    if order["status"] != "processing":
        return {"status": "error", "message": f"{order_id} is {order['status']}; the address can't be changed."}
    order["address"] = new_address
    _ledger.append({"tool": "update_address", "order_id": order_id, "new_address": new_address})
    return {"status": "updated", "order_id": order_id, "address": new_address}


def escalate_to_human(reason: str, tool_context: ToolContext) -> dict:
    """Hand the conversation to a human support teammate.

    Args:
        reason: Why a human is needed.
    """
    ticket_id = f"HO-{uuid.uuid4().hex[:8].upper()}"
    _ledger.append({"tool": "escalate_to_human", "reason": reason, "ticket_id": ticket_id})
    return {"status": "escalated", "ticket_id": ticket_id}
