"""Extract the user's explicit requirements and verify they survive enhancement.

This is the "requirement lock": every requirement found here is recorded with
its exact text, and the engine refuses to emit an enhanced prompt in which any
of them is missing. Extraction is conservative (it prefers whole sentences the
user wrote) so the lock checks real user words, not paraphrases.
"""

from __future__ import annotations

import re

from .document import PromptDoc
from .schema import LockCheck, Requirement

CONSTRAINT = re.compile(
    r"\b(must|must not|should not|shouldn't|never|don't|do not|only|at most|at least|no more than|"
    r"fewer than|less than|under \d+|maximum|minimum|limit(ed)? to|avoid|without|exactly|"
    r"make sure|ensure|always|keep it|keep the|no longer than|required?|needs? to)\b",
    re.I,
)
FORMAT = re.compile(
    r"\b(json|ya?ml|csv|table|bullet(s|ed)?( points?| list)?|numbered list|markdown|diff|patch|code block|"
    r"prose|paragraphs?|one (word|line|sentence|label)|plain text|html|xml)\b",
    re.I,
)
LENGTH = re.compile(
    r"\b(under|at most|no more than|fewer than|less than|maximum of|max|exactly|at least|between)?[ \t]*"
    r"\d+(\s*-\s*\d+)?[\s-]*(words?|sentences?|paragraphs?|lines?|characters?|chars|bullets?|points?|items?|tokens?)\b",
    re.I,
)
QUOTED = re.compile(r"\"[^\"\n]{1,120}\"|'[^'\n]{2,120}'|`[^`\n]{1,120}`|“[^”\n]{1,120}”")
AUDIENCE = re.compile(r"\b(for (an?|the|our) [\w -]{2,40}(audience|team|readers?|users?|customers?|executives?|leadership|beginners?|engineers?|developers?))\b", re.I)
TECHNOLOGY = re.compile(
    r"\b(python( \d(\.\d+)*)?|javascript|typescript|node(\.js)?|java|go(lang)?|rust|c\+\+|c#|ruby|php|kotlin|swift|"
    r"sql|postgres(ql)?( \d+)?|mysql|sqlite|react|vue|angular|django|flask|fastapi|spring|docker|kubernetes|terraform|"
    r"pytest|jest|bash|powershell)\b",
    re.I,
)


def extract(doc: PromptDoc) -> list[Requirement]:
    reqs: list[Requirement] = []
    seen: set[tuple[int, int]] = set()

    def add(kind: str, text: str, start: int, end: int) -> None:
        if (start, end) in seen or not text.strip():
            return
        seen.add((start, end))
        reqs.append(Requirement(id=f"R{len(reqs) + 1}", kind=kind, text=text, start=start, end=end))

    for s in doc.sentences:
        if CONSTRAINT.search(s.text):
            add("constraint", s.text, s.start, s.end)
    for kind, pat in (("length", LENGTH), ("format", FORMAT), ("literal", QUOTED), ("audience", AUDIENCE), ("technology", TECHNOLOGY)):
        for sp in doc.find_all(pat):
            text = sp.text.strip()
            if not text:
                continue
            start = sp.start + (len(sp.text) - len(sp.text.lstrip()))
            # skip fragments already covered by a whole constraint sentence
            if any(r.kind == "constraint" and r.start <= start and start + len(text) <= r.end for r in reqs):
                continue
            add(kind, text, start, start + len(text))
    reqs.sort(key=lambda r: r.start)
    for i, r in enumerate(reqs, 1):
        r.id = f"R{i}"
    return reqs


def check(requirements: list[Requirement], text: str) -> LockCheck:
    preserved: list[str] = []
    missing: list[str] = []
    for r in requirements:
        (preserved if r.text in text else missing).append(r.id)
    return LockCheck(preserved=preserved, missing=missing)


def is_subsequence(original: str, enhanced: str) -> bool:
    """True if every character of ``original`` appears in ``enhanced`` in order (only insertions happened)."""
    it = iter(enhanced)
    return all(ch in it for ch in original)
