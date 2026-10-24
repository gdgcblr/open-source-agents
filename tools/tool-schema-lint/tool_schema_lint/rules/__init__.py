"""Rule registry.

A rule is a function that inspects one tool (or, for set rules, the whole tool list) and
yields `Issue`s. Metadata - id, severity, targets, and the documentation the rule is
based on - lives on the `Rule` object so it can be listed with `--list-rules`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import NamedTuple

from ..models import Severity, ToolDef


class Issue(NamedTuple):
    path: str  # absolute JSON pointer in the input document
    message: str
    hint: str = ""
    tool: ToolDef | None = None  # set by set rules; per-tool rules leave it None


@dataclass(frozen=True)
class Rule:
    id: str
    severity: Severity
    summary: str
    source: str
    targets: frozenset[str] | None  # None means the rule applies to every target
    check: Callable[[ToolDef], Iterable[Issue]] | None = None
    check_set: Callable[[list[ToolDef]], Iterable[Issue]] | None = None


REGISTRY: dict[str, Rule] = {}


def _register(rule: Rule) -> None:
    if rule.id in REGISTRY:
        raise ValueError(f"duplicate rule id {rule.id}")
    REGISTRY[rule.id] = rule


def rule(rule_id: str, severity: Severity, summary: str, source: str,
         targets: Iterable[str] | None = None):
    """Register a per-tool rule."""
    def decorator(fn: Callable[[ToolDef], Iterable[Issue]]):
        _register(Rule(rule_id, severity, summary, source,
                       frozenset(targets) if targets is not None else None, check=fn))
        return fn
    return decorator


def set_rule(rule_id: str, severity: Severity, summary: str, source: str,
             targets: Iterable[str] | None = None):
    """Register a rule that inspects the full list of tools at once."""
    def decorator(fn: Callable[[list[ToolDef]], Iterable[Issue]]):
        _register(Rule(rule_id, severity, summary, source,
                       frozenset(targets) if targets is not None else None, check_set=fn))
        return fn
    return decorator


# Importing the modules registers their rules.
from . import anthropic, gemini, general, mcp, openai  # noqa: E402,F401
