"""Build the context packet a human receives when the agent escalates."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .gate import Verdict


def build_handoff(
    *,
    customer_id: str | None,
    user_texts: list[str],
    actions_taken: list[dict],
    proposed_action: dict | None,
    verdict: Verdict,
) -> dict:
    """Everything a human needs so the customer never has to repeat themselves."""
    return {
        "ticket_id": f"HO-{uuid.uuid4().hex[:8].upper()}",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "customer_id": customer_id,
        "customer_intent": user_texts[-1] if user_texts else None,
        "conversation": user_texts,
        "already_done": actions_taken,
        "proposed_action": proposed_action,
        "why_escalated": verdict.reason,
        "rule": verdict.rule,
        "detail": verdict.detail,
    }
