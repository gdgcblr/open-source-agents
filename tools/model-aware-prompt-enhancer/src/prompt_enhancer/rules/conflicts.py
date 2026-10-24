"""Conflict rules: requirements that cannot all be satisfied."""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..document import Span
from . import Finding, RuleContext, ev, negated, rule

_BRIEF = re.compile(r"\b(brief|briefly|concise(ly)?|short|succinct|one[- ](sentence|line|paragraph)|tl;?dr|keep it simple)\b", re.I)
_LONG = re.compile(r"\b(detailed|comprehensive|in[- ]depth|thorough(ly)?|exhaustive|as much detail|every detail|extensive(ly)?|long[- ]form)\b", re.I)
_LIMIT = re.compile(r"\b(under|at most|no more than|fewer than|less than|maximum of|max|exactly|at least|minimum of)\s+(\d+)\s*(words?|sentences?|paragraphs?|lines?|bullets?|items?|characters?)\b", re.I)


@rule("PE201", "conflicting-length", "conflict", "warning",
      description="Asks for brevity and exhaustive detail at once, or gives incompatible numeric limits.")
def conflicting_length(ctx: RuleContext) -> Iterator[Finding]:
    doc = ctx.doc
    brief, long_ = doc.find_all(_BRIEF), doc.find_all(_LONG)
    if brief and long_:
        b, lg = brief[0], long_[0]
        yield Finding(
            message=f"'{b.text}' and '{lg.text}' pull in opposite directions; the model will have to pick one.",
            remediation="Keep one, or scope them separately (for example 'a one-paragraph summary, then a detailed appendix').",
            evidence=[ev(b.text, b.start, b.end), ev(lg.text, lg.start, lg.end)],
            confidence=0.7,
        )
    by_unit: dict[str, list[tuple[str, int, re.Match[str], int]]] = {}
    for m in _LIMIT.finditer(doc.request):
        unit = m.group(3).lower().rstrip("s")
        by_unit.setdefault(unit, []).append((m.group(1).lower(), int(m.group(2)), m, m.start()))
    for unit, items in by_unit.items():
        uppers = [n for kind, n, _, _ in items if kind in {"under", "at most", "no more than", "fewer than", "less than", "maximum of", "max", "exactly"}]
        lowers = [n for kind, n, _, _ in items if kind in {"at least", "minimum of", "exactly"}]
        distinct_exact = {n for kind, n, _, _ in items if kind == "exactly"}
        if (uppers and lowers and max(lowers) > min(uppers)) or len(distinct_exact) > 1 or len(set(uppers)) > 1:
            yield Finding(
                message=f"Different limits are given for {unit}s: " + ", ".join(m.group(0) for _, _, m, _ in items) + ".",
                remediation="Keep a single limit, or say which part of the output each limit applies to.",
                evidence=[ev(m.group(0), s, s + len(m.group(0))) for _, _, m, s in items],
                confidence=0.75,
            )


_FORMATS = {
    "JSON": re.compile(r"\b(as|in|return|output|respond (with|in)|valid)\s+(a\s+)?json\b|\bjson (object|array|format|only)\b", re.I),
    "YAML": re.compile(r"\b(as|in)\s+ya?ml\b|\byaml (format|only)\b", re.I),
    "CSV": re.compile(r"\b(as|in)\s+(a\s+)?csv\b|\bcsv (format|only)\b", re.I),
    "a table": re.compile(r"\b(as|in)\s+a\s+(markdown\s+)?table\b", re.I),
    "prose": re.compile(r"\b(as|in)\s+(flowing\s+)?(prose|paragraphs)\b|\bno (bullet|lists?)\b", re.I),
    "bullet points": re.compile(r"\b(as|in)\s+(a\s+)?(bullet(ed)? (points|list)|bullets)\b", re.I),
}


@rule("PE202", "conflicting-output-format", "conflict", "warning",
      description="Requests more than one mutually exclusive output format for the same response.")
def conflicting_format(ctx: RuleContext) -> Iterator[Finding]:
    hits = [(name, ctx.doc.find_all(p)) for name, p in _FORMATS.items()]
    hits = [(n, spans) for n, spans in hits if spans]
    if len(hits) >= 2:
        names = [n for n, _ in hits]
        yield Finding(
            message="The prompt asks for the response " + " and ".join(f"in {n}" for n in names) + ".",
            remediation="Pick one format, or say which part of the output uses which format.",
            evidence=[ev(s[0].text, s[0].start, s[0].end) for _, s in hits],
            confidence=0.6,
        )


_POS = re.compile(r"\b(?:use|include|mention|add|always use|always include)\s+((?:the\s+)?[\w.+#-]+(?:\s+[\w.+#-]+)?)", re.I)
_NEG = re.compile(r"\b(?:don't|do not|never|avoid|without)\s+(?:use|using|include|including|mention|mentioning|add|adding)?\s*((?:the\s+)?[\w.+#-]+(?:\s+[\w.+#-]+)?)", re.I)
_STOP = {"the", "a", "an", "any", "it", "them", "this", "that"}


def _head(phrase: str) -> str:
    words = [w.strip(".,;:!?") for w in phrase.lower().split() if w.strip(".,;:!?") not in _STOP]
    return words[0] if words else ""


@rule("PE203", "contradictory-directives", "conflict", "warning",
      description="Tells the model to both use and not use the same thing.")
def contradictory(ctx: RuleContext) -> Iterator[Finding]:
    pos: dict[str, Span] = {}
    for sp in ctx.doc.find_all(_POS):
        if negated(ctx.doc.text, sp.start):
            continue
        m = _POS.match(sp.text)
        if m and _head(m.group(1)):
            pos.setdefault(_head(m.group(1)), sp)
    for sp in ctx.doc.find_all(_NEG):
        m = _NEG.match(sp.text)
        h = _head(m.group(1)) if m else ""
        if h and h in pos and not (pos[h].start <= sp.start < pos[h].end):
            p = pos[h]
            yield Finding(
                message=f"The prompt both asks for and forbids '{h}'; the model cannot follow both.",
                remediation="Remove one, or state when each applies.",
                evidence=[ev(p.text, p.start, p.end), ev(sp.text, sp.start, sp.end)],
                confidence=0.7,
            )
            return
