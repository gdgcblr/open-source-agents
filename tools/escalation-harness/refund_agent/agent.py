"""Threadline support agent: the demo agent the harness protects.

Run `adk web` from tools/escalation-harness and pick `refund_agent`.
Set HARNESS=off in .env to try the same agent without the harness.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models.base_llm import BaseLlm

from escalation_harness.adk import EscalationHarness

from . import store

HERE = Path(__file__).parent
load_dotenv(HERE.parent / ".env")

DEFAULT_MODEL = "gemini-3.5-flash-lite"

# The policy is also written into the prompt, so the baseline is what most teams
# ship today: rules the model is asked to follow, with nothing enforcing them.
INSTRUCTION = """You are the customer support assistant for Threadline, an online clothing store in Bengaluru.
You are talking to a signed-in customer. Help them with their orders: looking them up, refunds,
cancellations and delivery address changes. Use the tools to take actions, and never claim an
action happened unless a tool confirmed it.

Store policy:
- Refunds go only to the customer's original payment method.
- Refunds above ₹5,000 per order need a human approver: use escalate_to_human.
- If the customer asks for a human, or mentions legal action, use escalate_to_human.
- If a request is unclear (for example, which order), ask one short clarifying question instead of guessing.
- A delivery address must include a 6-digit PIN code.

If a tool result contains harness_blocked, follow its instruction exactly."""

TOOLS = [
    store.list_orders,
    store.issue_refund,
    store.cancel_order,
    store.update_address,
    store.escalate_to_human,
]


def build_agent(harness: EscalationHarness | None, model: str | BaseLlm | None = None) -> Agent:
    return Agent(
        name="threadline_support",
        model=model or os.getenv("MODEL_NAME", DEFAULT_MODEL),
        instruction=INSTRUCTION,
        tools=TOOLS,
        **(harness.callbacks() if harness else {}),
    )


def new_harness(handoff_dir: str | Path | None = None) -> EscalationHarness:
    return EscalationHarness(HERE / "policy.yaml", handoff_dir=handoff_dir)


root_agent = build_agent(
    None if os.getenv("HARNESS", "on").lower() == "off" else new_harness(HERE.parent / "handoffs")
)
