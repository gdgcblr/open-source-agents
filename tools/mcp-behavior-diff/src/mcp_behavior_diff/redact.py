"""Sanitise untrusted text (tool output, server stderr) before it is stored or shown.

Tool output comes from a server we do not control. Treat it as hostile data:
  * strip terminal escape sequences and control characters (terminal injection),
  * make invisible / bidirectional Unicode characters visible (Trojan-Source style tricks),
  * redact things that look like credentials (reports are often committed or pasted),
  * cap the size so a server cannot flood memory, disk or the terminal.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from typing import Any, Iterable

REDACTED = "[REDACTED]"

# Keys whose *values* are redacted wholesale. Narrow on purpose: over-matching would mask real changes.
SECRET_KEY_RE = re.compile(
    r"password|passwd|secret|token|api[_-]?key|authorization|credential|private[_-]?key|access[_-]?key", re.I
)
# Per-process key so equal secret values get equal fingerprints (a changed value is still
# visible in the diff) without exposing anything brute-forceable across runs.
_RUN_KEY = secrets.token_bytes(16)

_ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)?|[@-Z\\-_])")
# C0 controls except \t and \n, DEL, C1 controls.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
# Zero-width, bidi override/isolate, BOM, line/paragraph separators.
_INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u2028-\u202e\u2060-\u206f\ufeff]")

_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password|passwd)\b(\s*[:=]\s*)\S+"),
    # JSON text such as {"password": "x"}: structured results arrive as a text block, so the
    # key is only visible here, not to the structured-key redaction in clean_json.
    re.compile(
        r'(?i)("[^"\\\n]*(?:' + SECRET_KEY_RE.pattern + r')[^"\\\n]*"\s*:\s*)(?:"(?:[^"\\\n]|\\.)*"|[^\s,}\]]+)'
    ),
]
_MIN_LITERAL_SECRET_LEN = 6


def _escape_char(match: re.Match[str]) -> str:
    return f"\\u{ord(match.group(0)):04x}"


def sanitize_text(text: str) -> str:
    """Remove terminal escapes/control characters and make invisible characters visible."""
    text = _ANSI_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    return _INVISIBLE_RE.sub(_escape_char, text)


def redact_text(text: str, literal_secrets: Iterable[str] = ()) -> str:
    """Replace credential-looking substrings and any known literal secret values."""
    for secret in sorted({s for s in literal_secrets if len(s) >= _MIN_LITERAL_SECRET_LEN}, key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:  # keep the "key=" prefix, drop only the value
            text = pattern.sub(lambda m: m.group(0)[: m.start(1) - m.start(0)] + m.group(1) + REDACTED, text)
        else:
            text = pattern.sub(REDACTED, text)
    return text


def truncate_text(text: str, max_bytes: int) -> str:
    """Cap text to ``max_bytes`` of UTF-8, marking truncation."""
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    kept = raw[:max_bytes].decode("utf-8", errors="ignore")
    return f"{kept}\n[TRUNCATED: output exceeded {max_bytes} bytes]"


def clean_text(text: str, *, max_bytes: int, literal_secrets: Iterable[str] = ()) -> str:
    """Sanitise, then redact, then truncate (order matters: escapes could split a secret)."""
    return truncate_text(redact_text(sanitize_text(text), literal_secrets), max_bytes)


def _fingerprint(value: Any) -> str:
    digest = hmac.new(_RUN_KEY, repr(value).encode("utf-8"), hashlib.sha256).hexdigest()[:8]
    return f"{REDACTED[:-1]}:{digest}]"


def clean_json(value: Any, *, max_bytes: int, literal_secrets: Iterable[str] = ()) -> Any:
    """Recursively clean every string (keys and values) inside a JSON-like structure.

    Values stored under secret-looking keys (``{"password": "x"}``) are replaced by a
    run-scoped fingerprint, since pattern matching on the value alone cannot see them.
    """
    secrets_ = tuple(literal_secrets)
    if isinstance(value, str):
        return clean_text(value, max_bytes=max_bytes, literal_secrets=secrets_)
    if isinstance(value, list):
        return [clean_json(v, max_bytes=max_bytes, literal_secrets=secrets_) for v in value]
    if isinstance(value, dict):
        cleaned: dict[Any, Any] = {}
        for key, item in value.items():
            clean_key = clean_text(str(key), max_bytes=max_bytes, literal_secrets=secrets_)
            scalar = isinstance(item, (str, int, float, bool))
            if scalar and SECRET_KEY_RE.search(clean_key):
                cleaned[clean_key] = _fingerprint(item)
            else:
                cleaned[clean_key] = clean_json(item, max_bytes=max_bytes, literal_secrets=secrets_)
        return cleaned
    return value
