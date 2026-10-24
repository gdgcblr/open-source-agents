"""Prompt-injection detection.

PR content is untrusted. A README or PR body can try to talk the AI reviewer
into approving it. We flag such attempts for a human, and the LLM is never
able to clear a deterministic finding anyway (see agent.Arbiter).

Text is NFKC-normalised and look-alike Cyrillic/Greek letters are folded to
Latin before matching, so "Ignore" spelled with a Cyrillic letter o is still caught. Every
text file is scanned, whatever its extension.
"""

from __future__ import annotations

import re
import unicodedata

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
    # Paraphrases: addressing automated reviewers, or dictating the outcome.
    r"\b(?:note|message|instructions?|attention|notice)\s+(?:for|to)\s+(?:the\s+|any\s+|all\s+)?(?:automated|ai|llm|bot|machine)\b",
    r"\breport\s+(?:zero|no|0)\s+(?:issues|findings|problems|errors|violations)\b",
    r"\b(?:already|have)\s+(?:been\s+)?(?:verified|approved|reviewed)\s+this\s+(?:submission|pr|pull\s+request|contribution)\b",
    r"\b(?:give|assign|award)\s+(?:this|it|the\s+pr)\s+(?:a\s+)?(?:full|perfect|maximum|top|100)\b",
    r"\b(?:do\s+not|don't|never)\s+(?:flag|report|mention)\s+(?:any|this|these)\s+(?:issues?|findings?|problems?)\b",
]
COMPILED = [re.compile(p, re.I) for p in PATTERNS]
HIDDEN = re.compile("[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
HTML_COMMENT = re.compile(r"<!--(.*?)-->", re.S)
# Cyrillic and Greek letters that render like Latin ones.
CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s",
    "ԁ": "d", "ԛ": "q", "ԝ": "w", "һ": "h", "ӏ": "l", "к": "k", "м": "m", "т": "t", "в": "b", "н": "h",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T",
    "Х": "X", "І": "I", "Ј": "J", "Ѕ": "S",
    "α": "a", "ε": "e", "ι": "i", "ο": "o", "ρ": "p", "τ": "t", "υ": "u", "ν": "v", "κ": "k",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O",
    "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
})
WORD = re.compile(r"\w+")


def fold(text: str) -> str:
    """NFKC + confusable folding, so look-alike letters match the Latin patterns."""
    return unicodedata.normalize("NFKC", text).translate(CONFUSABLES)


def _mixed_script(word: str) -> bool:
    latin = cyr_greek = False
    for ch in word:
        if not ch.isalpha():
            continue
        if ch.isascii():
            latin = True
        else:
            name = unicodedata.name(ch, "")
            if name.startswith(("CYRILLIC", "GREEK")):
                cyr_greek = True
    return latin and cyr_greek


def _hidden(line: str) -> bool:
    """Invisible/bidi characters, except ZWNJ/ZWJ inside Indic or Arabic words, where they are normal spelling."""
    for m in HIDDEN.finditer(line):
        ch, i = m.group(0), m.start()
        if ch in "\u200c\u200d":
            prev = line[i - 1] if i else ""
            if prev and not prev.isascii() and unicodedata.category(prev)[0] in "LM":
                continue
        return True
    return False


def scan(text: str) -> list[tuple[int, str]]:
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        folded = fold(line)
        for rx in COMPILED:
            m = rx.search(folded)
            if m:
                hits.append((n, f"instruction aimed at the reviewer: \"{m.group(0)[:80]}\""))
                break
        else:
            mixed = next((w for w in WORD.findall(line) if _mixed_script(w)), None)
            if mixed:
                hits.append((n, f"word mixing Latin and Cyrillic/Greek look-alike letters (\"{mixed[:30]}\")"))
        if _hidden(line):
            hits.append((n, "invisible/bidirectional Unicode characters (can hide text from humans)"))
    for m in HTML_COMMENT.finditer(text):
        body = fold(m.group(1))
        if re.search(r"\b(AI|LLM|reviewer|assistant|bot|model)\b", body, re.I) and re.search(
            r"\b(approve|merge|ignore|pass|score|accept|you\s+(must|should|are))\b", body, re.I
        ):
            n = text[: m.start()].count("\n") + 1
            hits.append((n, "hidden HTML comment addressed to an AI reviewer"))
    return hits


def is_text(head: bytes) -> bool:
    return b"\0" not in head


def check(sub: Submission, policy: Policy) -> list[Finding]:
    out: list[Finding] = []
    sources = [("PR description", sub.body)] if sub.body else []
    for f in sub.project_files():
        if f.stat().st_size >= 500_000:
            continue
        try:
            raw = f.read_bytes()
        except OSError:
            continue
        if is_text(raw[:8192]):
            sources.append((str(f.relative_to(sub.root)), raw.decode("utf-8", "replace")))
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
