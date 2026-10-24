"""Clarity rules: objective, ambiguity, missing input context."""

from __future__ import annotations

import re
from collections.abc import Iterator

from . import Finding, RuleContext, add_line, ev, rule

_ACTION = re.compile(
    r"^(please\s+|kindly\s+)?(write|create|build|add|fix|refactor|summari[sz]e|extract|list|explain|compare|analy[sz]e|"
    r"translate|generate|draft|review|update|remove|delete|rename|convert|implement|test|document|find|make|design|"
    r"classify|describe|give|tell|show|help|plan|outline|evaluate|assess|research|investigate|identify|propose|"
    r"suggest|recommend|rewrite|edit|proofread|debug|optimi[sz]e|improve|check|verify|calculate|estimate|answer|"
    r"use|return|output|respond|produce|prepare|compose|tag|label|parse|map|merge|split|sort|format|count|predict)\b",
    re.I,
)
_REQUESTY = re.compile(r"\b(can|could|would|will) you\b|\bi (need|want|would like)\b|\bhelp me\b|\blet'?s\b|\?\s*$", re.I | re.M)


@rule("PE101", "missing-objective", "clarity", "warning",
      description="The prompt never says what the model should do or produce.")
def missing_objective(ctx: RuleContext) -> Iterator[Finding]:
    doc = ctx.doc
    if doc.word_count < 3 or "slash_command" in ctx.flags or not doc.sentences:
        return
    if any(_ACTION.match(s.text) for s in doc.sentences) or _REQUESTY.search(doc.request):
        return
    first = doc.sentences[0]
    yield Finding(
        message="No explicit instruction or question was found, so the model has to guess what to do with this text.",
        remediation="Start with what you want: an action verb ('Summarize...', 'Fix...') or a direct question.",
        evidence=[ev(first.text, first.start, first.end)],
        confidence=0.6,
        patches=[add_line(ctx, "Goal: {answer}", "State the objective explicitly.",
                          question="What should the model do or produce with this prompt?")],
    )


_VAGUE = re.compile(
    r"\b(etc\.?|and so on|stuff|things like that|somehow|properly|appropriate(ly)?|as needed|whatever|"
    r"nice|better|good enough|user[- ]friendly|faster|robust|clean(er)?|optimi[sz]e|improve)\b",
    re.I,
)
_MEASURABLE = re.compile(r"\d|\b(so that|by (reducing|removing|making|adding)|measured|metric|benchmark|p\d{2}|latency|ms|seconds?|percent|%)\b", re.I)


@rule("PE102", "ambiguous-terms", "clarity", "info",
      description="Subjective or open-ended words with no stated criterion (better, properly, etc.).")
def ambiguous_terms(ctx: RuleContext) -> Iterator[Finding]:
    for s in ctx.doc.sentences:
        if _MEASURABLE.search(s.text):
            continue
        for m in _VAGUE.finditer(s.text):
            term = m.group(0)
            yield Finding(
                message=f"'{term}' is open to interpretation and no criterion is given in this sentence.",
                remediation=f"Say what '{term}' means here, for example a measurable target or a concrete example.",
                evidence=[ev(s.text, s.start, s.end)],
                confidence=0.5,
                patches=[add_line(ctx, f"By '{term}' I mean: {{answer}}", f"Define '{term}'.",
                                  question=f"What does '{term}' mean concretely in this request?")],
            )
            break  # one finding per sentence keeps the report readable


_REFERENCE = re.compile(
    r"\b(the (following|attached|above|below|text|article|document|file|code|function|data|email|report|transcript|snippet|diff|logs?|table|spreadsheet|csv)|"
    r"this (code|file|function|text|article|document|data|email|report|transcript|snippet|diff|error|log|table|class|module|script)|"
    r"(see|shown|pasted|provided) (below|above))\b",
    re.I,
)
_FILE_REF = re.compile(r"\b[\w./-]+\.(py|js|ts|tsx|jsx|java|go|rs|rb|php|cs|cpp|c|h|sql|md|txt|json|ya?ml|csv|html|css|sh)\b")


@rule("PE103", "missing-input-context", "context", "warning",
      description="The prompt refers to material (the code below, the attached report) that is not included.")
def missing_input_context(ctx: RuleContext) -> Iterator[Finding]:
    doc = ctx.doc
    if doc.blocks or ctx.harness.mode == "augment":
        return  # content present, or an agent harness that can open files itself
    refs = doc.find_all(_REFERENCE)
    if not refs:
        return
    tail = doc.text[refs[-1].end:]
    if len(tail.strip()) > 200 or _FILE_REF.search(doc.text):
        return  # something substantial follows, or it names a file an agent can read
    r = refs[0]
    yield Finding(
        message=f"The prompt refers to '{r.text}' but no such content is included.",
        remediation="Paste the referenced material inside a delimited block (``` fences or <document> tags). "
                    "If your chat app attaches files separately, you can ignore this.",
        evidence=[ev(r.text, r.start, r.end)],
        confidence=0.65,
    )
