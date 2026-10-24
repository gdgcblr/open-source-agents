"""Diagnostic rule registry.

A rule is a function decorated with :func:`rule`. It receives a
:class:`RuleContext` and yields :class:`Finding` objects. Rules are grouped by
category in sibling modules, which register themselves on import. To add a
rule, write a function in the right module (or a new module listed in
``_MODULES``) and give it a new stable id; nothing else needs to change.

Rule ids are stable public identifiers (``PE101`` ...): never reuse or renumber them.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from collections.abc import Callable, Iterable

from ..document import PromptDoc
from ..schema import Evidence, HarnessProfile, ModelProfile, Patch, Requirement, Severity


@dataclass
class RuleContext:
    doc: PromptDoc
    task_type: str
    intent: str
    requirements: list[Requirement]
    flags: set[str]
    profile: ModelProfile
    harness: HarnessProfile


@dataclass
class Finding:
    message: str
    remediation: str
    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 0.8
    severity: Severity | None = None  # overrides the rule default
    patches: list[Patch] = field(default_factory=list)


RuleFunc = Callable[[RuleContext], Iterable[Finding]]


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    category: str
    severity: Severity
    tasks: frozenset[str] | None  # None = applies to every task type
    description: str
    func: RuleFunc


_REGISTRY: dict[str, Rule] = {}
_MODULES = ("clarity", "conflicts", "output", "coding", "research", "verbosity", "safety")


def rule(id: str, name: str, category: str, severity: Severity, tasks: Iterable[str] | None = None, description: str = "") -> Callable[[RuleFunc], RuleFunc]:
    def deco(func: RuleFunc) -> RuleFunc:
        if id in _REGISTRY:
            raise ValueError(f"duplicate rule id {id}")
        _REGISTRY[id] = Rule(id, name, category, severity, frozenset(tasks) if tasks else None, description or (func.__doc__ or "").strip(), func)
        return func
    return deco


def all_rules() -> list[Rule]:
    for m in _MODULES:
        importlib.import_module(f"{__name__}.{m}")
    return sorted(_REGISTRY.values(), key=lambda r: r.id)


def ev(text: str, start: int, end: int) -> Evidence:
    return Evidence(text=text, start=start, end=end)


def anchor(ctx: RuleContext) -> int:
    """Offset just after the user's last instruction sentence (before any trailing context)."""
    return ctx.doc.sentences[-1].end if ctx.doc.sentences else len(ctx.doc.text)


def add_line(ctx: RuleContext, line: str, rationale: str, *, question: str | None = None, auto: bool = False, order: int = 0) -> Patch:
    """A patch that inserts one new line after the user's instructions.

    Use ``{answer}`` in ``line`` for information only the user can provide;
    such patches are never applied until the user supplies the answer.
    """
    pos = anchor(ctx)
    return Patch(
        id="", rule_id="", op="insert", start=pos, end=pos, new="\n" + line, rationale=rationale,
        auto=auto, needs_input="{answer}" in line, question=question, order=order,
    )


_NEGATION_BEFORE = __import__("re").compile(r"(\bnot|n't|\bnever|\bno|\bavoid|\bwithout|\bnor)\s+(\w+\s+){0,1}$", __import__("re").I)


def negated(text: str, start: int) -> bool:
    """True if the word at ``start`` is directly preceded by a negation ("don't add", "never use")."""
    return bool(_NEGATION_BEFORE.search(text[max(0, start - 30):start]))
