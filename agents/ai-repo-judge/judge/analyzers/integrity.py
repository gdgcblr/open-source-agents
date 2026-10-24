"""Attempts to manipulate AI judges, and Trojan Source (bidirectional control characters).

Many submissions are security tools that *discuss* or *test* prompt injection, so quoted examples,
test data and lines about detection are not attempts. Strong = addressed to graders/reviewers, or hidden
from human readers (HTML comments); weak = bare injection phrasing in prose.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from judge.models import Finding
from judge.workspace import Workspace

DIM = "security"
INJECTION_PATTERNS = [
    re.compile(
        r"(?i)\bignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\s+"
        r"(?:instructions|prompts|rules|directions)"
    ),
    re.compile(r"(?i)\bdisregard\s+(?:the\s+|all\s+|any\s+)?(?:previous|prior|above|rubric|scoring|instructions)"),
    re.compile(
        r"(?i)\b(?:give|award|assign|rate|score)\s+(?:this|it|me|us|the\s+(?:project|submission|repo"
        r"(?:sitory)?|pr|code))\s+(?:a\s+|the\s+)?(?:perfect|full|maximum|max|top|highest|100|10\s*/\s*10|"
        r"5\s*/\s*5)\b"
    ),
    re.compile(
        r"(?i)\b(?:ai|llm|automated|bot)\s+(?:judges?|graders?|reviewers?|evaluators?)\s*[:,-]\s*"
        r"(?:please\s+)?(?:give|score|rate|approve|ignore|mark)"
    ),
    re.compile(r"(?i)\bnew\s+system\s+prompt\b|<\s*/?\s*system\s*>|\[\s*/?\s*system\s*\]|<\|im_start\|>"),
]
DIRECTED = {2, 3}  # indexes of the patterns that address graders or ask for a score
# Only bidi overrides/isolates (Trojan Source). Zero-width joiners are needed by Kannada and other scripts, and emoji.
BIDI = re.compile("[\u202a-\u202e\u2066-\u2069]")
QUOTED = re.compile(r"\"[^\"]*\"|`[^`]*`|“[^”]*”|‘[^’]*’|'[^'\n]{8,}'")
DISCUSSION = re.compile(
    r"(?i)inject|detect|defen[cs]e|guard|attack|adversar|malicious|poison|jailbreak|e\.g\.|"
    r"such as|for example|scan|flag|sanitiz|reject|resist|evidence|rule|pattern|block|threat"
)
CODE_LANGS = {"Python", "JavaScript", "TypeScript", "Go", "Rust", "Java", "Shell", "Ruby"}
COMMENT_PREFIXES = ("#", "//", "/*", "*")


def _quoted(line: str, start: int, end: int) -> bool:
    return any(m.start() <= start and end <= m.end() for m in QUOTED.finditer(line))


def _reader_lines(text: str, code: bool) -> Iterator[tuple[int, str, bool]]:
    """Lines a human reader sees as prose, as (line_no, line, hidden). In code only comments qualify,
    because strings are data the program handles; in markdown, fenced code blocks are skipped unless
    they sit inside an HTML comment, whose content is hidden from readers."""
    in_fence = in_comment = False
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not code and stripped.startswith("```"):
            in_fence = not in_fence
            continue
        hidden = in_comment or "<!--" in line
        if "<!--" in line and "-->" not in line.split("<!--", 1)[1]:
            in_comment = True
        elif in_comment and "-->" in line:
            in_comment = False
        if code and not stripped.startswith(COMMENT_PREFIXES):
            continue
        if in_fence and not hidden:
            continue
        yield i, line, hidden


def _classify(line: str, hidden: bool) -> bool | None:
    """True = directed at graders (strong), False = bare injection phrasing (weak), None = not an attempt."""
    for n, pat in enumerate(INJECTION_PATTERNS):
        m = pat.search(line)
        if not m:
            continue
        if not hidden and (_quoted(line, m.start(), m.end()) or DISCUSSION.search(line)):
            continue
        return hidden or n in DIRECTED
    return None


def _attempt(rel: str, i: int, line: str, hidden: bool, directed: bool) -> Finding:
    return Finding(
        dimension=DIM,
        severity="high" if directed else "medium",
        file=rel,
        line=i,
        snippet=line.strip()[:160],
        title=("Instructions aimed at AI judges/reviewers" + (" (hidden)" if hidden else ""))
        if directed
        else "Prompt-injection phrasing in prose",
        detail="Treated as an attempt to manipulate automated review; the judge ignored it."
        if directed
        else "Not quoted or framed as an example. If it is an example, quote it.",
        fix="Remove instructions aimed at reviewers or graders."
        if directed
        else "Put example attack strings in quotes or a code block.",
    )


def _bidi(rel: str, i: int) -> Finding:
    return Finding(
        dimension=DIM,
        severity="medium",
        file=rel,
        line=i,
        title="Bidirectional control characters",
        detail="Bidi overrides can make code render differently from how it runs (Trojan Source).",
        fix="Remove U+202A–U+202E and U+2066–U+2069 characters (write them as \\u escapes if you need them).",
    )


def scan(ws: Workspace) -> tuple[list[Finding], int, int]:
    """(findings, strong count, weak count)."""
    findings: list[Finding] = []
    strong = weak = 0
    for rel in ws.files:
        if ws.is_data_file(rel) or ws.language(rel) == "JSON" or rel.endswith((".lock", ".svg")):
            continue
        text = ws.read(rel) or ""
        for i, line in enumerate(text.splitlines(), 1):
            if BIDI.search(line):
                strong += 1
                findings.append(_bidi(rel, i))
        for i, line, hidden in _reader_lines(text, ws.language(rel) in CODE_LANGS):
            directed = _classify(line, hidden)
            if directed is not None:
                strong += directed
                weak += not directed
                findings.append(_attempt(rel, i, line, hidden, directed))
    return findings, strong, weak
