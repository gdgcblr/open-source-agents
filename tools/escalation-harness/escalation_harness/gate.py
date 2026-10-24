"""Decide whether a proposed tool call should run, or stop for a question, a human, or a refusal.

Everything here is deterministic: no model calls, so the same input always
gets the same verdict and every verdict names the rule that produced it.
"""

from __future__ import annotations

import operator
import re
from dataclasses import dataclass, field
from enum import Enum

from .policy import Condition, Policy

_OPS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}


class Decision(str, Enum):
    ACT = "act"
    CLARIFY = "clarify"
    ESCALATE = "escalate"
    REFUSE = "refuse"


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    rule: str
    reason: str
    detail: dict = field(default_factory=dict)


@dataclass
class Evidence:
    """What the agent can legitimately know when it proposes a tool call."""

    user_texts: list[str] = field(default_factory=list)
    tool_outputs: list[str] = field(default_factory=list)
    # (tool, args) for calls the gate already allowed in this session
    prior_actions: list[tuple[str, dict]] = field(default_factory=list)


def check_message(policy: Policy, text: str) -> Verdict | None:
    """Return an ESCALATE verdict if a customer message hits an always-escalate phrase."""
    lowered = text.lower()
    for trigger, phrases in policy.escalate_on_phrases.items():
        for phrase in phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", lowered):
                return Verdict(
                    Decision.ESCALATE,
                    rule=f"phrase:{trigger}",
                    reason=f"Customer message matched '{phrase}' ({trigger}).",
                    detail={"trigger": trigger, "phrase": phrase},
                )
    return None


def _mentions(text: str, value: str) -> bool:
    """Whole-token match, so "ORD-100" is not found in "ORD-1001"."""
    return bool(value) and re.search(rf"(?<![\w-]){re.escape(value)}(?![\w-])", text) is not None


def _coerce(a, b):
    try:
        return float(a), float(b)
    except (TypeError, ValueError):
        return str(a), str(b)


def _holds(cond: Condition, tool: str, args: dict, evidence: Evidence) -> tuple[bool, object]:
    if cond.arg not in args:
        return False, None
    value = args[cond.arg]
    if cond.cumulative_by:
        key = args.get(cond.cumulative_by)
        earlier = [
            float(prev[cond.arg])
            for name, prev in evidence.prior_actions
            if name == tool and prev.get(cond.cumulative_by) == key and cond.arg in prev
        ]
        value = sum(earlier) + float(value)
    left, right = _coerce(value, cond.value)
    return _OPS[cond.op](left, right), value


def decide(policy: Policy, tool: str, args: dict, evidence: Evidence) -> Verdict:
    spec = policy.tools.get(tool)
    if spec is None:
        return Verdict(
            Decision(policy.unknown_tool),
            rule="unknown_tool",
            reason=f"'{tool}' is not covered by the policy.",
        )

    # 1. Hard rules: never allowed, whoever asks.
    for cond in spec.refuse_if:
        hit, value = _holds(cond, tool, args, evidence)
        if hit:
            return Verdict(
                Decision.REFUSE,
                rule=f"refuse_if:{cond.arg}{cond.op}{cond.value}",
                reason=cond.reason,
                detail={"arg": cond.arg, "value": value},
            )

    # 2. Ambiguity: ask before acting on something the customer never chose.
    user_text = "\n".join(evidence.user_texts)
    tool_text = "\n".join(evidence.tool_outputs)
    for arg, pattern in spec.grounded_args.items():
        value = str(args.get(arg, ""))
        if _mentions(user_text, value):
            continue
        candidates = sorted(set(re.findall(pattern, tool_text)))
        if value not in candidates:
            return Verdict(
                Decision.CLARIFY,
                rule=f"ungrounded:{arg}",
                reason=f"'{value}' for {arg} was never given by the customer or returned by a tool.",
                detail={"arg": arg, "value": value, "candidates": candidates},
            )
        if len(candidates) > 1:
            return Verdict(
                Decision.CLARIFY,
                rule=f"ambiguous:{arg}",
                reason=f"The customer did not say which {arg}; {len(candidates)} are possible.",
                detail={"arg": arg, "value": value, "candidates": candidates},
            )
    for arg, pattern in spec.required_patterns.items():
        if not re.search(pattern, str(args.get(arg, ""))):
            return Verdict(
                Decision.CLARIFY,
                rule=f"incomplete:{arg}",
                reason=f"{arg} is missing required detail (expected to match {pattern}).",
                detail={"arg": arg, "value": args.get(arg)},
            )
    for arg, pattern in spec.grounded_parts.items():
        for part in re.findall(pattern, str(args.get(arg, ""))):
            if not _mentions(user_text, part):
                return Verdict(
                    Decision.CLARIFY,
                    rule=f"ungrounded_part:{arg}",
                    reason=f"'{part}' in {arg} was never given by the customer.",
                    detail={"arg": arg, "value": part},
                )

    # 3. Allowed in principle, but above what an agent may do alone.
    for cond in spec.escalate_if:
        hit, value = _holds(cond, tool, args, evidence)
        if hit:
            return Verdict(
                Decision.ESCALATE,
                rule=f"escalate_if:{cond.arg}{cond.op}{cond.value}",
                reason=cond.reason,
                detail={"arg": cond.arg, "value": value},
            )

    return Verdict(Decision.ACT, rule=f"allow:{spec.risk}", reason="All policy checks passed.")
