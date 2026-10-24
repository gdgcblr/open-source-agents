"""Apply registered rules to normalized tools."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from .models import FORMAT_OPENAI, TARGET_OPENAI_STRICT, Finding, Severity, ToolDef
from .rules import REGISTRY, Rule

TOKEN_BUDGET_RULE = Rule(
    "G016", Severity.ERROR, "Tool definitions fit within the --max-tokens budget",
    "Estimate: compact JSON characters / 4 (not a provider tokenizer)", None,
)
REGISTRY.setdefault(TOKEN_BUDGET_RULE.id, TOKEN_BUDGET_RULE)


@dataclass
class LintResult:
    findings: list[Finding]
    tool_count: int
    token_estimate: int
    targets: list[str] = field(default_factory=list)

    def count(self, severity: Severity) -> int:
        return sum(1 for f in self.findings if f.severity == severity)


def active_targets(tool: ToolDef, targets: Iterable[str] | None) -> set[str]:
    """Targets for one tool: the requested ones, or the tool's own format by default."""
    active = set(targets) if targets else {tool.source_format}
    if FORMAT_OPENAI in active and tool.strict:
        active.add(TARGET_OPENAI_STRICT)
    return active


def estimate_tokens(tools: list[ToolDef]) -> int:
    """Rough token count of the definitions as a model would receive them (chars / 4)."""
    total = 0
    for tool in tools:
        text = json.dumps(tool.raw, separators=(",", ":"), ensure_ascii=False)
        total += math.ceil(len(text) / 4)
    return total


def lint(tools: list[ToolDef], targets: Iterable[str] | None = None, disabled: Iterable[str] = (),
         max_tokens: int | None = None, file: str = "") -> LintResult:
    targets = list(targets or [])
    disabled = set(disabled)
    order = {id(t): i for i, t in enumerate(tools)}
    per_tool = {id(t): active_targets(t, targets) for t in tools}
    collected: list[tuple[int, Finding]] = []

    def applies(rule: Rule, tool: ToolDef) -> bool:
        return rule.targets is None or bool(rule.targets & per_tool[id(tool)])

    def add(rule: Rule, tool: ToolDef | None, path: str, message: str, hint: str) -> None:
        label = tool.label if tool is not None else "*"
        idx = order[id(tool)] if tool is not None else -1
        collected.append((idx, Finding(rule.id, rule.severity, label, path, message, hint, file)))

    for rule in sorted(REGISTRY.values(), key=lambda r: r.id):
        if rule.id in disabled:
            continue
        if rule.check is not None:
            for tool in tools:
                if applies(rule, tool):
                    for issue in rule.check(tool):
                        add(rule, tool, issue.path, issue.message, issue.hint)
        elif rule.check_set is not None:
            subset = [t for t in tools if applies(rule, t)]
            if subset:
                for issue in rule.check_set(subset):
                    add(rule, issue.tool, issue.path, issue.message, issue.hint)

    tokens = estimate_tokens(tools)
    if max_tokens is not None and tokens > max_tokens and TOKEN_BUDGET_RULE.id not in disabled:
        add(TOKEN_BUDGET_RULE, None, "",
            f"tool definitions are ~{tokens} tokens, over the budget of {max_tokens}",
            "Shorten verbose descriptions, drop unused tools, or split the tool set.")

    collected.sort(key=lambda item: (item[0], item[1].path, -item[1].severity, item[1].rule_id))
    used = sorted(set().union(*per_tool.values())) if per_tool else []
    return LintResult([f for _, f in collected], len(tools), tokens, used)
