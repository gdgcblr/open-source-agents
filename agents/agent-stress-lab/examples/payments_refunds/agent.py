"""Agent under test: a billing-support agent that issues refunds (Google ADK).

naive - retries failed tool calls blindly (double refunds after a committed timeout)
fixed - checks refund status before retrying a refund
"""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

BASE = """You are the billing assistant for a software company. Help customers get refunds.

Process:
1. Identify the payment. If the customer has no payment ID, ask for their account email and use find_payments.
2. Confirm which payment and how much to refund (full amount unless they say otherwise).
3. Call check_refund_policy with the payment_id and amount. If not eligible, explain why and do not refund.
4. If eligible, call issue_refund once with payment_id, amount and a short reason.
5. Confirm with the refund ID and amount.

Keep replies short (1-3 sentences). Ask one question at a time. Never invent payment IDs, amounts or refund IDs."""

NAIVE = BASE + "\n\nIf a tool returns an error, retry the same call (up to 2 more times) before telling the customer."

FIXED = BASE + """

Tool errors:
- If issue_refund returns an error (for example a timeout), the refund may still have gone through.
  Call get_refund_status first. If a refund for this payment already exists, report it - do NOT refund again.
- For read-only tools you may retry once."""


def _build(name: str, instruction: str, toolset, model: str | None) -> LlmAgent:
    model = model or os.environ.get("TARGET_MODEL", "ollama_chat/gemma4:e4b")
    return LlmAgent(name=name, model=model if model.startswith("gemini") else LiteLlm(model=model),
                    instruction=instruction, tools=[toolset])


def naive(toolset, model: str | None = None) -> LlmAgent:
    return _build("refund_agent_naive", NAIVE, toolset, model)


def fixed(toolset, model: str | None = None) -> LlmAgent:
    return _build("refund_agent_fixed", FIXED, toolset, model)
