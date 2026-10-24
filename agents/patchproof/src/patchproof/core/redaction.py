"""Secret redaction utilities for evidence excerpts and logs."""

from __future__ import annotations

import re

REDACTION_PLACEHOLDER = "[REDACTED_SECRET]"

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # GitHub tokens
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    # OpenAI / Anthropic / generic sk- tokens
    re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_\-]{16,}\b"),
    # AWS Access Key ID
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # Private keys
    re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
        r"[\s\S]*?"
        r"-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    ),
    # Bearer tokens
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]{20,}=*"),
    # Key/value secret assignments
    re.compile(
        r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|password|github_token)"
        r"\s*[:=]\s*['\"]?([A-Za-z0-9\-._~+/]{12,})['\"]?"
    ),
)


def redact_secrets(text: str) -> tuple[str, bool]:
    """Redact common token, password, and private-key patterns from text.

    Returns:
        Tuple of (redacted_text, was_redacted).
    """
    if not text:
        return text, False

    redacted = text
    was_redacted = False

    for pattern in _SECRET_PATTERNS:
        if pattern.groups == 2:
            new_text, count = pattern.subn(rf"\1={REDACTION_PLACEHOLDER}", redacted)
        else:
            new_text, count = pattern.subn(REDACTION_PLACEHOLDER, redacted)
        if count > 0:
            was_redacted = True
            redacted = new_text

    return redacted, was_redacted

