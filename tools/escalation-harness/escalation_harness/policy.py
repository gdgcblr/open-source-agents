"""Load an escalation policy from YAML into typed, validated objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

OPS = {">", ">=", "<", "<=", "==", "!="}
RISKS = {"read", "reversible", "irreversible", "money", "handoff"}
DECISIONS = {"act", "clarify", "escalate", "refuse"}


@dataclass(frozen=True)
class Condition:
    arg: str
    op: str
    value: object
    reason: str
    # Sum `arg` across earlier allowed calls to the same tool that share this
    # arg's value (e.g. order_id), so a limit cannot be dodged by splitting.
    cumulative_by: str | None = None


@dataclass(frozen=True)
class ToolPolicy:
    risk: str
    # arg -> regex matching valid ids. The value must come from the user, or be
    # the only id of that shape that any tool has returned.
    grounded_args: dict[str, str] = field(default_factory=dict)
    # arg -> regex the value must contain (e.g. a 6-digit PIN code).
    required_patterns: dict[str, str] = field(default_factory=dict)
    # arg -> regex for parts of the value the customer must have said themselves,
    # so the model cannot fill them in with something plausible.
    grounded_parts: dict[str, str] = field(default_factory=dict)
    refuse_if: tuple[Condition, ...] = ()
    escalate_if: tuple[Condition, ...] = ()


@dataclass(frozen=True)
class Policy:
    tools: dict[str, ToolPolicy]
    # trigger name -> phrases that always hand the conversation to a human
    escalate_on_phrases: dict[str, tuple[str, ...]]
    unknown_tool: str = "escalate"


def _conditions(raw: list[dict] | None, where: str) -> tuple[Condition, ...]:
    conditions = []
    for item in raw or []:
        if item.get("op") not in OPS:
            raise ValueError(f"{where}: op must be one of {sorted(OPS)}, got {item.get('op')!r}")
        conditions.append(
            Condition(
                arg=item["arg"],
                op=item["op"],
                value=item["value"],
                reason=item["reason"],
                cumulative_by=item.get("cumulative_by"),
            )
        )
    return tuple(conditions)


def parse_policy(raw: dict) -> Policy:
    tools = {}
    for name, spec in (raw.get("tools") or {}).items():
        risk = spec.get("risk")
        if risk not in RISKS:
            raise ValueError(f"tools.{name}.risk must be one of {sorted(RISKS)}, got {risk!r}")
        tools[name] = ToolPolicy(
            risk=risk,
            grounded_args=dict(spec.get("grounded_args") or {}),
            required_patterns=dict(spec.get("required_patterns") or {}),
            grounded_parts=dict(spec.get("grounded_parts") or {}),
            refuse_if=_conditions(spec.get("refuse_if"), f"tools.{name}.refuse_if"),
            escalate_if=_conditions(spec.get("escalate_if"), f"tools.{name}.escalate_if"),
        )
    unknown_tool = raw.get("unknown_tool", "escalate")
    if unknown_tool not in DECISIONS:
        raise ValueError(f"unknown_tool must be one of {sorted(DECISIONS)}, got {unknown_tool!r}")
    phrases = {
        trigger: tuple(p.lower() for p in items)
        for trigger, items in (raw.get("escalate_on_phrases") or {}).items()
    }
    return Policy(tools=tools, escalate_on_phrases=phrases, unknown_tool=unknown_tool)


def load_policy(path: str | Path) -> Policy:
    with open(path, encoding="utf-8") as f:
        return parse_policy(yaml.safe_load(f) or {})
