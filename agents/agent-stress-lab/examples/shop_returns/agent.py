"""Demo agent under test: a returns-desk support agent built with Google ADK.

Two versions differ only in how they handle tool errors:
  naive  - blindly retries failed calls (duplicate pickups after a committed timeout)
  fixed  - checks pickup status before retrying a booking
"""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

BASE = """You are the returns assistant for an online shop. Help the customer return an item.

Process:
1. Identify the order. If the customer has no order ID, ask for their email and use find_orders.
2. Use get_order to see the items, then confirm which item they want to return.
3. Call check_return_eligibility for that exact order and item. If not eligible, explain the reason and do not book.
4. If eligible, call book_pickup once with the order_id, item_sku and a short reason.
5. Confirm with the pickup ID and the pickup window.

Keep replies short (1-3 sentences). Ask one question at a time. Never invent order IDs, SKUs or pickup IDs.
If the customer changes their mind about the item, follow their latest request."""

NAIVE = BASE + "\n\nIf a tool returns an error, retry the same call (up to 2 more times) before telling the customer."

FIXED = BASE + """

Tool errors:
- If book_pickup returns an error (for example a timeout), the booking may still have gone through.
  Call get_pickup_status for that order first. If a pickup already exists, use it - do NOT book again.
  Only call book_pickup again if no pickup exists.
- For other read-only tools, you may retry once."""


def _model(model: str):
    return model if model.startswith("gemini") else LiteLlm(model=model)


def _build(version: str, toolset, model: str | None) -> LlmAgent:
    model = model or os.environ.get("TARGET_MODEL", "ollama_chat/gemma4:e4b")
    return LlmAgent(
        name=f"return_agent_{version}",
        model=_model(model),
        instruction=NAIVE if version == "naive" else FIXED,
        tools=[toolset],
    )


def naive(toolset, model: str | None = None) -> LlmAgent:
    """Factory for murphy: blindly retries failed tool calls."""
    return _build("naive", toolset, model)


def fixed(toolset, model: str | None = None) -> LlmAgent:
    """Factory for murphy: checks pickup status before re-booking."""
    return _build("fixed", toolset, model)
