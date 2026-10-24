"""Redaction primitives.

Rule of the project: raw secret values never leave the detector stage. Everything downstream
(LLM prompts, logs, reports, exceptions) only sees the output of these functions.
"""

from __future__ import annotations

import math
import re
from collections import Counter

_HEX = re.compile(r"^[0-9a-fA-F]+$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_B64 = re.compile(r"^[A-Za-z0-9+/_\-]+={0,2}$")

# Fixed vocabulary of obviously-synthetic words. Reporting which of these appear lets the LLM
# recognise placeholders even though the value itself is redacted.
PLACEHOLDER_WORDS = (
    "changeme", "change_me", "your", "example", "sample", "placeholder", "dummy", "fake",
    "test", "todo", "xxxx", "redacted", "insert", "replace", "secret_here", "password",
    "notreal", "not_real", "foobar", "default",
)


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in Counter(s).values())


def char_classes(s: str) -> int:
    return sum(
        bool(re.search(p, s)) for p in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]")
    )


def is_uuid(s: str) -> bool:
    return bool(_UUID.match(s))


def describe_shape(value: str) -> str:
    """Coarse, non-reversible description of a value's alphabet."""
    if is_uuid(value):
        return "uuid"
    if _HEX.match(value):
        return "hex"
    if re.fullmatch(r"[A-Za-z0-9]+", value):
        return "alnum"
    if _B64.match(value):
        return "base64-like"
    return "mixed"


def redact_value(value: str, keep: int = 0) -> str:
    """e.g. `sk_live_51H****(32 chars, alnum)`.

    `keep` is the number of leading characters allowed to remain; it is capped at a third
    of the length so short values are never mostly revealed.
    """
    n = len(value)
    keep = 0 if n < 12 else max(0, min(keep, n // 3))
    return f"{value[:keep]}****({n} chars, {describe_shape(value)})"


def placeholder_hints(value: str) -> list[str]:
    """Non-secret hints derived from a value (fixed vocabulary + shape only)."""
    hints: list[str] = []
    low = value.lower()
    words = [w for w in PLACEHOLDER_WORDS if w in low]
    if words:
        hints.append("contains placeholder-like words: " + ", ".join(words))
    if re.search(r"(.)\1{5,}", value):
        hints.append("contains a long run of one repeated character")
    if re.fullmatch(r"[<{\[].*[>}\]]", value):
        hints.append("wrapped in <>/{}/[] like a template placeholder")
    if is_uuid(value):
        hints.append("has UUID shape")
    elif _HEX.match(value) and len(value) in (32, 40, 64, 128):
        hints.append(f"is {len(value)} hex chars: shape of an MD5/SHA digest or git SHA")
    return hints


_OPAQUE = re.compile(r"[A-Za-z0-9+/=_\-]{24,}")


def _opaque_spans(line: str):
    for m in _OPAQUE.finditer(line):
        v = m.group(0)
        if (
            re.search(r"[0-9]", v)
            and re.search(r"[A-Za-z]", v)
            and shannon_entropy(v) >= 3.5
        ):
            yield m.start(), m.end()


def redact_line(line: str, max_len: int = 240, skip_redacted: bool = False) -> str:
    """Replace every detected secret and every long opaque token in `line`."""
    from .detectors import find_matches  # local import: detectors imports this module

    spans: list[tuple[int, int, int]] = [
        (m.start, m.end, m.rule.keep if not m.rule.keep_whole else -1)
        for m in find_matches(line)
        if not (skip_redacted and "****" in m.value)
    ]
    for s, e in _opaque_spans(line):
        if not any(s < e2 and s2 < e for s2, e2, _ in spans):
            spans.append((s, e, 0))
    out = line
    for s, e, keep in sorted(spans, reverse=True):
        if keep == -1:  # public marker text such as a PEM header
            continue
        out = out[:s] + redact_value(line[s:e], keep) + out[e:]
    out = out.rstrip("\n\r")
    return out if len(out) <= max_len else out[:max_len] + "...(truncated)"
