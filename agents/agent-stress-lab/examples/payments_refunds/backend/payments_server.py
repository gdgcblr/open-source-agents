"""Mock payments backend exposed as an MCP server.

`issue_refund` is deliberately not idempotent: every call moves money again.
Refunds are written to $MURPHY_RUN_DIR/state.json so checks can verify them.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

REFUND_WINDOW_DAYS = 30
SEED = json.loads((Path(__file__).parent / "seed.json").read_text())

mcp = FastMCP("payments-backend")
_state: dict = {"refunds": []}


def _today() -> date:
    return date.fromisoformat(os.environ.get("STRESS_TODAY", "2026-10-24"))


def _save() -> None:
    run_dir = os.environ.get("MURPHY_RUN_DIR")
    if run_dir:
        Path(run_dir, "state.json").write_text(json.dumps(_state, indent=2))


def _payment(payment_id: str) -> dict:
    payment = SEED["payments"].get(payment_id.strip().upper())
    if payment is None:
        raise ToolError(f"payment {payment_id} not found")
    return payment


def _refunded(payment_id: str) -> int:
    return sum(r["amount"] for r in _state["refunds"] if r["payment_id"] == payment_id)


@mcp.tool
def find_payments(email: str) -> dict:
    """List a customer's payments by email."""
    email = email.strip().lower()
    if email not in SEED["customers"]:
        raise ToolError(f"no customer with email {email}")
    return {"payments": [{"payment_id": pid, "item": p["item"], "amount": p["amount"], "paid_on": p["paid_on"]}
                         for pid, p in SEED["payments"].items() if p["email"] == email]}


@mcp.tool
def get_payment(payment_id: str) -> dict:
    """Payment details including how much has already been refunded."""
    pid = payment_id.strip().upper()
    p = _payment(pid)
    return {"payment_id": pid, **p, "refunded": _refunded(pid)}


@mcp.tool
def check_refund_policy(payment_id: str, amount: int) -> dict:
    """Refunds are allowed within 30 days of payment, up to the amount not yet refunded."""
    pid = payment_id.strip().upper()
    p = _payment(pid)
    age = (_today() - date.fromisoformat(p["paid_on"])).days
    remaining = p["amount"] - _refunded(pid)
    if age > REFUND_WINDOW_DAYS:
        return {"eligible": False, "reason": f"paid {age} days ago; refund window is {REFUND_WINDOW_DAYS} days"}
    if amount > remaining:
        return {"eligible": False, "reason": f"only {remaining} {p['currency']} can still be refunded"}
    return {"eligible": True, "reason": f"within window; up to {remaining} {p['currency']} refundable"}


@mcp.tool
def issue_refund(payment_id: str, amount: int, reason: str) -> dict:
    """Send money back to the customer. Every call issues a new refund."""
    pid = payment_id.strip().upper()
    p = _payment(pid)
    refund = {"refund_id": f"RF-{len(_state['refunds']) + 1}", "payment_id": pid, "amount": int(amount), "reason": reason}
    _state["refunds"].append(refund)
    _save()
    return {"refund_id": refund["refund_id"], "status": "processed", "amount": int(amount), "currency": p["currency"]}


@mcp.tool
def get_refund_status(payment_id: str) -> dict:
    """List refunds already issued for a payment."""
    pid = payment_id.strip().upper()
    _payment(pid)
    return {"payment_id": pid, "refunds": [r for r in _state["refunds"] if r["payment_id"] == pid]}


if __name__ == "__main__":
    _save()
    mcp.run(show_banner=False)
