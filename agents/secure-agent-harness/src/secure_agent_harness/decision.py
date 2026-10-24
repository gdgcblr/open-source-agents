"""Typed decision seam for Jev-style routing; local policy remains authoritative."""
from typing import Protocol
from .models import Decision


class DecisionGate(Protocol):
    def evaluate(self, action_name: str, arguments: dict, requires_approval: bool) -> Decision:
        ...


class LocalDecisionGate:
    """Deterministic baseline. Replace with an optional Jev adapter if desired."""

    def evaluate(self, action_name: str, arguments: dict, requires_approval: bool) -> Decision:
        if requires_approval:
            return Decision("review", "Tool is configured to require human approval.", 1.0)
        if action_name not in {"calculator", "get_utc_time", "remember_fact"}:
            return Decision("block", "Action is not in the local policy allowlist.", 1.0)
        if action_name == "remember_fact":
            fact = str(arguments.get("fact", ""))
            if any(marker in fact.casefold() for marker in ("ignore all previous instructions", "system prompt")):
                return Decision("review", "Memory content resembles an instruction override.", 0.95)
        return Decision("allow", "Allowed by deterministic local policy.", 1.0)
