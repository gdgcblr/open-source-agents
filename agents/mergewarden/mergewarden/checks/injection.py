"""Prompt-injection detection.

PR content is untrusted. A README or PR body can try to talk the AI reviewer
into approving it. We flag such attempts for a human, and the LLM is never
able to clear a deterministic finding anyway (see pipeline.merge_findings).
"""

from __future__ import annotations

import re

from ..models import Criterion, Finding, Severity, Submission
from ..policy import Policy

PATTERNS = [
    r"\bignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\s+(?:instructions|rules|prompts?)",
    r"\bdisregard\s+(?:all\s+|the\s+)?(?:previous|prior|above|system)\s+\w+",
    r"\b(?:AI|LLM|automated|bot)\s+(?:reviewer|reviewers|agent|assistant)s?\s*[:,]?\s*(?:you\s+must|please)?\s*(?:approve|merge|pass|accept)",
    r"\b(?:approve|merge|accept)\s+this\s+(?:PR|pull\s+request|submission)\s+(?:immediately|without|regardless)",
    r"\byou\s+are\s+now\s+(?:a|an|in)\b",
    r"\b(?:system\s+prompt|developer\s+message)\s*[:=]",
    r"\bmark\s+(?:all|every)\s+(?:checks?|items?)\s+as\s+(?:passed|complete)",
]
HIDDEN = re.compile("[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
HTML_COMMENT = re.compile(r"<!--(.*?)-->", re.S)
TEXT_EXT = {".md", ".txt", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".html", ""}


def scan(text: str) -> list[tuple[int, str]]:
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        for pat in PATTERNS:
            m = re.search(pat, line, re.I)
            if m:
                hits.append((n, f"instruction aimed at the reviewer: \"{m.group(0)[:80]}\""))
                break
        if HIDDEN.search(line):
            hits.append((n, "invisible/bidirectional Unicode characters (can hide text from humans)"))
    for m in HTML_COMMENT.finditer(text):
        body = m.group(1)
        if re.search(r"\b(AI|LLM|reviewer|assistant|bot|model)\b", body, re.I) and re.search(
            r"\b(approve|merge|ignore|pass|score|accept|you\s+(must|should|are))\b", body, re.I
        ):
            n = text[: m.start()].count("\n") + 1
            hits.append((n, "hidden HTML comment addressed to an AI reviewer"))
    return hits


def check(sub: Submission, policy: Policy) -> list[Finding]:
    out: list[Finding] = []
    sources = [("PR description", sub.body)] if sub.body else []
    for f in sub.project_files():
        if f.suffix in TEXT_EXT and f.stat().st_size < 500_000:
            try:
                sources.append((str(f.relative_to(sub.root)), f.read_text(encoding="utf-8")))
            except (UnicodeDecodeError, OSError):
                pass
    for where, text in sources:
        done = set()
        for line, what in scan(text):
            if line in done:  # one finding per line is enough
                continue
            done.add(line)
            out.append(Finding(
                "safety.prompt-injection", Severity.MAJOR, Criterion.SECURITY,
                f"Possible prompt injection: {what}. A human must review this PR.",
                file=None if where == "PR description" else where, line=line,
                rule=policy.rule("safety.loops"),
            ))
    return out
