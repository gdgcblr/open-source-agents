"""Coding-task rules."""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..requirements import TECHNOLOGY
from . import Finding, RuleContext, add_line, ev, negated, rule

_BUILD = re.compile(r"\b(write|implement|create|build|add|generate|code|develop|scaffold)\b", re.I)
_FILE = re.compile(r"\b[\w./-]+\.(py|js|ts|tsx|jsx|java|go|rs|rb|php|cs|cpp|c|h|kt|swift|sql|sh)\b")
_QUALITY = re.compile(r"\b(tests?|testing|edge cases?|error handling|errors?|exceptions?|validat(e|ion)|invalid|empty input|null|corner cases?|fail(ure)?s?)\b", re.I)
_BUG = re.compile(r"\b(fix|debug|bug|broken|crash(es|ing)?|fails?|failing|error|exception|doesn'?t work|not working|wrong)\b", re.I)
_DETAIL = re.compile(r"\b(expected|should|instead|traceback|stack ?trace|error message|returns?|output is|got|but)\b", re.I)


def _builds(ctx: RuleContext) -> list:
    return [h for h in ctx.doc.find_all(_BUILD) if not negated(ctx.doc.text, h.start)]


@rule("PE401", "coding-missing-language", "coding", "warning", tasks={"coding"},
      description="Asks for new code without naming the language, runtime or existing file.")
def missing_language(ctx: RuleContext) -> Iterator[Finding]:
    doc = ctx.doc
    if ctx.intent == "question" or doc.blocks or doc.find_all(TECHNOLOGY) or _FILE.search(doc.text):
        return
    hits = _builds(ctx)
    if not hits:
        return
    h = hits[0]
    yield Finding(
        message="New code is requested but no language, framework or target file is named.",
        remediation="Name the language/runtime and version, and any framework or existing file the code must fit.",
        evidence=[ev(h.text, h.start, h.end)],
        confidence=0.7,
        patches=[add_line(ctx, "Language/runtime: {answer}", "Avoid the model picking a stack for you.",
                          question="Which language, version and framework should the code use?")],
    )


@rule("PE402", "coding-missing-quality-bar", "coding", "info", tasks={"coding"},
      description="New-code request with no expectations for tests, error handling or edge cases.")
def missing_quality(ctx: RuleContext) -> Iterator[Finding]:
    doc = ctx.doc
    if ctx.intent in {"question", "advisory"} or not _builds(ctx) or _QUALITY.search(doc.request) or doc.word_count < 6:
        return
    yield Finding(
        message="No expectations are given for tests, error handling or edge cases, so the model decides how robust the code is.",
        remediation="Say whether you want tests and which edge cases or failure modes matter.",
        confidence=0.5,
        patches=[add_line(ctx, "Tests and error handling: {answer}", "Set the quality bar.",
                          question="Should the code include tests, and which edge cases or errors must it handle?")],
    )


@rule("PE403", "bug-report-missing-details", "coding", "warning", tasks={"coding"},
      description="Asks to fix a bug without the error, the observed behaviour or the expected behaviour.")
def bug_details(ctx: RuleContext) -> Iterator[Finding]:
    doc = ctx.doc
    hits = doc.find_all(_BUG)
    if not hits or doc.blocks or _DETAIL.search(doc.request) or ctx.harness.mode == "augment":
        return
    h = hits[0]
    yield Finding(
        message="A fix is requested but the prompt gives neither the error output nor the expected behaviour.",
        remediation="Include the exact error or failing output and what you expected to happen instead.",
        evidence=[ev(h.text, h.start, h.end)],
        confidence=0.6,
        patches=[add_line(ctx, "Observed vs expected: {answer}", "Give the model a definition of 'fixed'.",
                          question="What happens now (error text), and what should happen instead?")],
    )
