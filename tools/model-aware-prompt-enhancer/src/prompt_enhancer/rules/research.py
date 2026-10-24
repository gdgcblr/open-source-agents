"""Research and analysis rules."""

from __future__ import annotations

import re
from collections.abc import Iterator

from . import Finding, RuleContext, add_line, ev, rule

_SCOPE = re.compile(r"\b(focus on|limit(ed)? to|only (consider|include|cover)|between \d{4}|since \d{4}|in \d{4}|from \d{4}|in (india|the us|europe|[A-Z][a-z]+)|for (our|my|the) |criteria|scope|dimensions?)\b", re.I)
_TIME = re.compile(r"\b(latest|current(ly)?|recent(ly)?|today|this (year|month|week)|up[- ]to[- ]date|right now|as of now|trending)\b(?!\s+(record|entry|row|item|commit|value|version of|message|element|file)s?\b)", re.I)
_DATE = re.compile(r"\b(19|20)\d{2}\b|\bas of\b", re.I)
_CITE = re.compile(r"\b(sources?|cite|citations?|references?|links?|evidence|according to|footnotes?)\b", re.I)


@rule("PE501", "research-missing-scope", "research", "info", tasks={"research"},
      description="Open research question without scope (time range, region, criteria).")
def missing_scope(ctx: RuleContext) -> Iterator[Finding]:
    doc = ctx.doc
    if doc.blocks or _SCOPE.search(doc.request) or not 5 <= doc.word_count <= 40:
        return
    yield Finding(
        message="The research question has no scope (time range, region, comparison criteria), so depth and focus will vary.",
        remediation="Add the scope that matters: period, region, criteria to compare on, or what to leave out.",
        confidence=0.5,
        patches=[add_line(ctx, "Scope: {answer}", "Bound the research.",
                          question="What scope should the answer cover (period, region, criteria)?")],
    )


@rule("PE502", "time-sensitive-without-date", "research", "info",
      description="Asks for current information without a date; models have training cutoffs.")
def time_sensitive(ctx: RuleContext) -> Iterator[Finding]:
    hits = ctx.doc.find_all(_TIME)
    if not hits or _DATE.search(ctx.doc.request):
        return
    h = hits[0]
    yield Finding(
        message=f"'{h.text}' depends on today's date, but models answer from training data with a cutoff unless a search tool is available.",
        remediation="State today's date or the period you mean, and supply sources or enable a search/grounding tool if freshness matters.",
        evidence=[ev(h.text, h.start, h.end)],
        confidence=0.6,
    )


@rule("PE503", "research-no-citation-expectation", "research", "info", tasks={"research"},
      description="Research request that does not say whether claims need sources.")
def no_citations(ctx: RuleContext) -> Iterator[Finding]:
    doc = ctx.doc
    if doc.blocks or _CITE.search(doc.request) or doc.word_count < 12:
        return
    yield Finding(
        message="The prompt does not say whether claims must be backed by sources, which makes unsupported statements harder to spot.",
        remediation="Ask for sources or citations for factual claims, or say explicitly that they are not needed.",
        confidence=0.45,
    )
