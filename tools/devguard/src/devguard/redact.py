"""Secret redaction utilities for DevGuard.

Redacts common credentials, tokens, and sensitive strings before persistent logging
or sending context to external AI providers.
"""

from __future__ import annotations

import re


# Compiled regex patterns for common secret formats
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Google API Keys
    ("GEMINI_KEY", re.compile(r"AIza[0-9A-Za-z-_]{35}")),
    # OpenAI API Keys
    ("OPENAI_KEY", re.compile(r"\bsk-[a-zA-Z0-9_-]{20,}\b")),
    # GitHub Personal Access Tokens
    ("GITHUB_PAT", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36}\b")),
    # GitLab Personal Access Tokens
    ("GITLAB_PAT", re.compile(r"\bglpat-[a-zA-Z0-9_\-]{20,}\b")),
    # Slack Tokens
    ("SLACK_TOKEN", re.compile(r"\bxox[baprs]-[0-9a-zA-Z-]{10,}\b")),
    # Generic Bearer Tokens
    ("BEARER_TOKEN", re.compile(r"(?i)\bbearer\s+[a-zA-Z0-9_\-\.=:~+/]{15,}\b")),
    # Authorization Headers
    ("AUTH_HEADER", re.compile(r"(?i)\bauthorization:\s*(?:basic|bearer)\s+[a-zA-Z0-9_\-\.=:~+/]+")),
    # Generic Key/Secret assignments in configs or logs
    (
        "GENERIC_SECRET",
        re.compile(
            r"(?i)\b(api_key|apikey|secret_key|private_key|auth_token|access_token|password|passwd|db_password)"
            r"\s*[:=]\s*['\"]?([A-Za-z0-9_\-!@#$%^&*+=.~]{8,})['\"]?"
        ),
    ),
    # Database URIs with credentials (e.g. postgres://user:pass@host:5432/db)
    (
        "DB_URI",
        re.compile(r"\b([a-zA-Z][a-zA-Z0-9+.-]+://[^:\s]+):([^@\s]+)@"),
    ),
    # Private Key Blocks
    (
        "PRIVATE_KEY",
        re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"),
    ),
]


def redact_secrets(text: str) -> str:
    """Redact known secret patterns from the provided text.

    Args:
        text: Input string potentially containing sensitive tokens or credentials.

    Returns:
        Sanitized string with sensitive tokens replaced by redaction placeholders.
    """
    if not text:
        return ""

    redacted = text

    # Redact private key blocks first
    redacted = PATTERNS[9][1].sub("[REDACTED_PRIVATE_KEY]", redacted)

    # Redact database credentials
    redacted = PATTERNS[8][1].sub(r"\1:[REDACTED_DB_PASSWORD]@", redacted)

    # Redact generic key=value secrets
    def _replace_generic(match: re.Match[str]) -> str:
        key_name = match.group(1)
        return f"{key_name}=[REDACTED]"

    redacted = PATTERNS[7][1].sub(_replace_generic, redacted)

    # Redact Authorization headers
    redacted = PATTERNS[6][1].sub("Authorization: [REDACTED]", redacted)

    # Redact Bearer tokens
    redacted = PATTERNS[5][1].sub("Bearer [REDACTED]", redacted)

    # Redact provider-specific keys (Google, OpenAI, GitHub, GitLab, Slack)
    for name, pattern in PATTERNS[:5]:
        redacted = pattern.sub(f"[REDACTED_{name}]", redacted)

    return redacted

