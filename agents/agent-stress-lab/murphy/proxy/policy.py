"""Declarative tool-call policies, evaluated before every call.

Observations use ground truth (what the upstream actually did), so a call that
committed but was reported to the agent as a timeout still counts.
"""

from __future__ import annotations

from collections import Counter
from fnmatch import fnmatch

from murphy.config.schema import BudgetRule, IdempotentRule, MaxCallsRule, RequiresBeforeRule, Rule


def key_of(args: dict, fields: list[str]) -> tuple[str, ...]:
    return tuple(str(args.get(f, "")).strip().upper() for f in fields)


class PolicyEngine:
    def __init__(self, rules: list[Rule], mode: str = "monitor") -> None:
        self.rules = rules
        self.mode = mode
        self.total = 0
        self.per_tool: Counter[str] = Counter()
        self.done: dict[str, set[tuple]] = {}  # rule id -> keys that succeeded upstream
        self.prior_ok: dict[str, set[tuple]] = {}  # rule id -> prior keys satisfied

    @property
    def enforcing(self) -> bool:
        return self.mode == "enforce"

    def check(self, tool: str, args: dict) -> list[str]:
        if self.mode == "off":
            return []
        self.total += 1
        self.per_tool[tool] += 1
        violations = []
        for rule in self.rules:
            if isinstance(rule, BudgetRule):
                if self.total > rule.max_tool_calls:
                    violations.append(rule.id)
            elif not fnmatch(tool, rule.tool):
                continue
            elif isinstance(rule, MaxCallsRule):
                if self.per_tool[tool] > rule.max:
                    violations.append(rule.id)
            elif isinstance(rule, IdempotentRule):
                if key_of(args, rule.key) in self.done.get(rule.id, set()):
                    violations.append(rule.id)
            elif isinstance(rule, RequiresBeforeRule):
                if key_of(args, rule.match) not in self.prior_ok.get(rule.id, set()):
                    violations.append(rule.id)
        return violations

    def observe(self, tool: str, args: dict, result: dict | None, upstream_ok: bool) -> None:
        if self.mode == "off" or not upstream_ok:
            return
        for rule in self.rules:
            if isinstance(rule, IdempotentRule) and fnmatch(tool, rule.tool):
                self.done.setdefault(rule.id, set()).add(key_of(args, rule.key))
            elif isinstance(rule, RequiresBeforeRule) and fnmatch(tool, rule.prior):
                res = result or {}
                if all(res.get(k) == v for k, v in rule.prior_result.items()):
                    self.prior_ok.setdefault(rule.id, set()).add(key_of(args, rule.match))
