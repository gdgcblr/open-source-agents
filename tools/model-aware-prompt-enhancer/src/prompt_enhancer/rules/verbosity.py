"""Verbosity rules: duplicated instructions and filler."""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..schema import Patch
from . import Finding, RuleContext, ev, rule


def _norm(s: str) -> str:
    return re.sub(r"[^\w]+", " ", s.lower()).strip()


@rule("PE601", "duplicate-instruction", "verbosity", "info",
      description="The same sentence appears more than once.")
def duplicates(ctx: RuleContext) -> Iterator[Finding]:
    seen: dict[str, int] = {}
    text = ctx.doc.text
    for i, s in enumerate(ctx.doc.sentences):
        key = _norm(s.text)
        if len(key.split()) < 3:
            continue
        if key in seen:
            first = ctx.doc.sentences[seen[key]]
            # remove the repeat plus the whitespace in front of it
            start = s.start
            while start > 0 and text[start - 1] in " \t":
                start -= 1
            yield Finding(
                message="This instruction is repeated word for word.",
                remediation="Keep one copy; repetition adds tokens without adding information.",
                evidence=[ev(first.text, first.start, first.end), ev(s.text, s.start, s.end)],
                confidence=0.95,
                patches=[Patch(id="", rule_id="", op="replace", start=start, end=s.end, new="",
                               rationale="Remove the exact duplicate; the first occurrence is kept.")],
            )
        else:
            seen[key] = i


_FILLER = re.compile(
    r"\b(i was wondering if you could( possibly)?|if it'?s not too much trouble|i would (really )?appreciate it if you could|"
    r"please kindly|kindly please|as an ai( language model)?|i hope you can help( me)?( with this)?|thanks? in advance)\b",
    re.I,
)


@rule("PE602", "filler-phrases", "verbosity", "info",
      description="Politeness or filler phrases that carry no instruction.")
def filler(ctx: RuleContext) -> Iterator[Finding]:
    hits = ctx.doc.find_all(_FILLER)
    if hits:
        yield Finding(
            message="Filler phrases add tokens but no instruction: " + ", ".join(f"'{h.text}'" for h in hits[:3]) + ".",
            remediation="Optional: state the request directly. This is a token-cost note, not an accuracy problem.",
            evidence=[ev(h.text, h.start, h.end) for h in hits[:3]],
            confidence=0.8,
        )
