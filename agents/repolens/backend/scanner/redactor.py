"""
RepoLens — Secret Redactor

Redacts likely secrets from strings before they are:
  - Sent to Gemini
  - Written to application logs
  - Stored in evidence fields of reports

This is a defence-in-depth measure. Scanner findings should already avoid
capturing raw secret values; this provides an additional safety net.
"""
from __future__ import annotations

import re
from typing import List, Optional, Pattern, Tuple

# ---------------------------------------------------------------------------
# Redaction patterns
# Each entry: (label, compiled_regex, redact_full_match)
# If redact_full_match=True -> replace entire match.
# If redact_full_match=False -> replace with a custom sub function.
# ---------------------------------------------------------------------------

_REDACTION_PLACEHOLDER = "[REDACTED]"

# Patterns that match the entire secret (no capture groups needed for replacement)
_SIMPLE_PATTERNS: List[Tuple[str, Pattern]] = [
    # Generic high-entropy: key=VALUE style (>= 20 chars after =)
    (
        "GENERIC_SECRET",
        re.compile(
            r'(?i)(?:api[_\-]?key|secret[_\-]?key|access[_\-]?token|auth[_\-]?token'
            r'|private[_\-]?key|password|passwd|pwd|token|credential)\s*[=:]\s*'
            r'["\']?([A-Za-z0-9+/=._\-]{20,})["\']?',
        ),
    ),
    # GitHub personal access token (classic) ghp_
    (
        "GITHUB_PAT",
        re.compile(r'ghp_[A-Za-z0-9]{36}'),
    ),
    # GitHub OAuth token gho_
    (
        "GITHUB_OAUTH",
        re.compile(r'gho_[A-Za-z0-9]{36}'),
    ),
    # AWS access key
    (
        "AWS_ACCESS_KEY",
        re.compile(r'AKIA[0-9A-Z]{16}'),
    ),
    # Google API key (AIzaSy prefix ~39 chars total)
    (
        "GOOGLE_API_KEY",
        re.compile(r'AIza[0-9A-Za-z\-_]{33,}'),
    ),
    # Slack token
    (
        "SLACK_TOKEN",
        re.compile(r'xox[baprs]-[0-9A-Za-z\-]{10,}'),
    ),
]

# URL embedded credentials — replaces scheme://user:PASSWORD@host -> scheme://[REDACTED]@host
_URL_CRED_RE = re.compile(
    r'([a-zA-Z][a-zA-Z0-9+\-.]*://)([^:@\s/]+):([^@\s/]+)(@)'
)


def _redact_url_creds(text: str) -> str:
    """Replace password portion of basic-auth URLs."""
    return _URL_CRED_RE.sub(r'\1\2:[REDACTED]\4', text)


def redact(text: str) -> str:
    """
    Return a copy of *text* with likely secrets replaced by [REDACTED].
    The original text is never mutated.
    """
    if not text:
        return text
    result = text
    # Apply simple full-match patterns
    for _label, pattern in _SIMPLE_PATTERNS:
        result = pattern.sub(_REDACTION_PLACEHOLDER, result)
    # Apply URL credential redaction separately (preserves URL structure)
    result = _redact_url_creds(result)
    return result


def redact_evidence(evidence: Optional[str], max_bytes: int = 2048) -> Optional[str]:
    """
    Apply redaction and truncate to max_bytes.
    Returns None if evidence is None.
    """
    if evidence is None:
        return None
    redacted = redact(evidence)
    # Truncate to max_bytes without breaking multibyte chars
    encoded = redacted.encode("utf-8", errors="replace")
    if len(encoded) > max_bytes:
        redacted = encoded[:max_bytes].decode("utf-8", errors="replace") + " [TRUNCATED]"
    return redacted


def contains_likely_secret(text: str) -> bool:
    """Return True if *text* appears to contain a secret pattern."""
    for _label, pattern in _SIMPLE_PATTERNS:
        if pattern.search(text):
            return True
    if _URL_CRED_RE.search(text):
        return True
    return False
