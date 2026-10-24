"""Lightweight secret detection (no network, no dependencies)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key ID", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI-style API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY")),
]

# NAME = "value" where NAME looks like a credential and value looks random.
GENERIC = re.compile(
    r"""\b([A-Za-z0-9_]*(?:API_?KEY|SECRET|TOKEN|PASSWORD|PASSWD|ACCESS_?KEY)[A-Za-z0-9_]*)"""
    r"""\s*[:=]\s*["']?([^\s"'#]{16,})["']?""",
    re.IGNORECASE,
)

PLACEHOLDER_HINTS = (
    "your", "xxx", "changeme", "change_me", "change-me", "example", "placeholder",
    "dummy", "sample", "replace", "here", "<", "...", "none", "null", "redacted",
    "insert", "todo", "fake", "test",
)
CODE_CHARS = set("()[]{}$<>,;")
ALLOW_MARKER = "lint:allow-secret"


@dataclass
class SecretHit:
    line: int
    label: str
    snippet: str


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {c: value.count(c) for c in set(value)}
    return -sum((n / len(value)) * math.log2(n / len(value)) for n in counts.values())


def _redact(value: str) -> str:
    return value[:4] + "…" if len(value) > 4 else "…"


def _is_placeholder(value: str) -> bool:
    low = value.lower()
    return any(h in low for h in PLACEHOLDER_HINTS)


def scan_text(text: str) -> list[SecretHit]:
    hits: list[SecretHit] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        matched = False
        for label, pattern in PATTERNS:
            m = pattern.search(line)
            if m:
                hits.append(SecretHit(lineno, label, _redact(m.group(0))))
                matched = True
                break
        if matched:
            continue
        m = GENERIC.search(line)
        if not m:
            continue
        value = m.group(2)
        if _is_placeholder(value) or CODE_CHARS & set(value):
            continue
        if _entropy(value) < 3.2:
            continue
        hits.append(SecretHit(lineno, f"Hard-coded value for {m.group(1)}", _redact(value)))
    return hits
