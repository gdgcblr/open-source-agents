"""Mock shop backend exposed as an MCP server.

Deterministic seed data, a fixed "today", and a deliberately non-idempotent
`book_pickup` so retry bugs in agents become visible as duplicate pickups.
State is written to $MURPHY_RUN_DIR/state.json after every side effect so the
judge can verify outcomes against ground truth.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

RETURN_WINDOW_DAYS = 30
SEED = json.loads((Path(__file__).parent / "seed.json").read_text())

mcp = FastMCP("shop-backend")
_state: dict = {"pickups": [], "side_effect_calls": []}


def _today() -> date:
    return date.fromisoformat(os.environ.get("STRESS_TODAY", "2026-10-24"))


def _save_state() -> None:
    run_dir = os.environ.get("MURPHY_RUN_DIR")
    if run_dir:
        Path(run_dir, "state.json").write_text(json.dumps(_state, indent=2))


def _order(order_id: str) -> dict:
    order = SEED["orders"].get(order_id.strip().upper())
    if order is None:
        raise ToolError(f"order {order_id} not found")
    return order


def _item(order: dict, item_sku: str) -> dict:
    for item in order["items"]:
        if item["sku"] == item_sku.strip().upper():
            return item
    raise ToolError(f"item {item_sku} not in order")


@mcp.tool
def find_orders(email: str) -> dict:
    """List a customer's orders by email address."""
    email = email.strip().lower()
    if email not in SEED["customers"]:
        raise ToolError(f"no customer with email {email}")
    orders = [
        {"order_id": oid, "delivered_on": o["delivered_on"], "items": [i["name"] for i in o["items"]]}
        for oid, o in SEED["orders"].items()
        if o["email"] == email
    ]
    return {"email": email, "orders": orders}


@mcp.tool
def get_order(order_id: str) -> dict:
    """Get order details: delivery date and items (sku, name, size, final_sale)."""
    order = _order(order_id)
    return {"order_id": order_id.strip().upper(), "delivered_on": order["delivered_on"], "items": order["items"]}


@mcp.tool
def check_return_eligibility(order_id: str, item_sku: str) -> dict:
    """Check whether an item can be returned (within 30 days of delivery, not final sale)."""
    order = _order(order_id)
    item = _item(order, item_sku)
    age = (_today() - date.fromisoformat(order["delivered_on"])).days
    if item["final_sale"]:
        return {"eligible": False, "reason": "final sale items cannot be returned"}
    if age > RETURN_WINDOW_DAYS:
        return {"eligible": False, "reason": f"delivered {age} days ago; return window is {RETURN_WINDOW_DAYS} days"}
    return {"eligible": True, "reason": f"delivered {age} days ago, within window"}


@mcp.tool
def book_pickup(order_id: str, item_sku: str, reason: str) -> dict:
    """Book a courier pickup for a return. Every call creates a new pickup."""
    order = _order(order_id)
    item = _item(order, item_sku)
    pickup = {
        "id": f"PU-{len(_state['pickups']) + 1}",
        "order_id": order_id.strip().upper(),
        "item_sku": item["sku"],
        "reason": reason,
    }
    _state["pickups"].append(pickup)
    _state["side_effect_calls"].append(
        {"tool": "book_pickup", "args": {"order_id": order_id, "item_sku": item_sku, "reason": reason}, "ts": time.time()}
    )
    _save_state()
    return {"pickup_id": pickup["id"], "status": "scheduled", "window": "tomorrow 10:00-14:00"}


@mcp.tool
def get_pickup_status(order_id: str) -> dict:
    """List pickups already booked for an order."""
    oid = order_id.strip().upper()
    _order(oid)
    return {"order_id": oid, "pickups": [p for p in _state["pickups"] if p["order_id"] == oid]}


if __name__ == "__main__":
    _save_state()
    mcp.run(show_banner=False)
