"""Log and stack trace sanitizer for the Incident Analyzer.

This module provides security guardrails by scrubbing sensitive information
from logs, stack traces, and error outputs before they are sent to an LLM
for analysis. It ensures zero credential leakage to external APIs.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SanitizationReport:
    """Report of what was sanitized from the input."""
    original_length: int = 0
    sanitized_length: int = 0
    redactions: list[str] = field(default_factory=list)

    @property
    def was_modified(self) -> bool:
        """Return True if any redactions were applied."""
        return len(self.redactions) > 0


# Compiled regex patterns for performance.
# Each entry: (human-readable name, compiled pattern, replacement string)
_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # API Keys & Tokens (common patterns)
    ("API Key (generic)", re.compile(
        r"""(?i)(?:api[_-]?key|apikey|api[_-]?secret|secret[_-]?key)\s*[=:]\s*['"]?([a-zA-Z0-9_\-]{20,})['"]?"""
    ), r"<REDACTED_API_KEY>"),

    # JWT Tokens (checked before generic auth headers for specific redaction)
    ("JWT Token", re.compile(
        r'eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+'
    ), "<REDACTED_JWT>"),

    # Bearer/Authorization tokens
    ("Authorization Header", re.compile(
        r"""(?i)(?:bearer|token|authorization)\s*[=:]\s*['"]?([a-zA-Z0-9_\-\.]{20,})['"]?"""
    ), r"<REDACTED_AUTH_TOKEN>"),

    # AWS Access Key IDs
    ("AWS Access Key", re.compile(
        r'(?:AKIA|ASIA)[A-Z0-9]{16}'
    ), "<REDACTED_AWS_KEY>"),

    # AWS Secret Access Key
    ("AWS Secret Key", re.compile(
        r"""(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*['"]?([a-zA-Z0-9/+=]{40})['"]?"""
    ), "<REDACTED_AWS_SECRET>"),

    # GCP Service Account private key indicator
    ("GCP Service Account", re.compile(
        r'"private_key"\s*:\s*"-----BEGIN [A-Z ]+ KEY-----'
    ), '"private_key": "<REDACTED_PRIVATE_KEY>"'),

    # Generic PEM private key blocks
    ("Private Key Block", re.compile(
        r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'
    ), "<REDACTED_PRIVATE_KEY_BLOCK>"),

    # Password patterns
    ("Password", re.compile(
        r"""(?i)(?:password|passwd|pwd)\s*[=:]\s*['"]?(\S{4,})['"]?"""
    ), r"<REDACTED_PASSWORD>"),

    # Database connection strings
    ("Database URI", re.compile(
        r'(?:mysql|postgres|postgresql|mongodb|redis|amqp):\/\/[^\s]+'
    ), "<REDACTED_DB_URI>"),

    # Email addresses
    ("Email Address", re.compile(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    ), "<REDACTED_EMAIL>"),

    # IPv4 addresses
    ("IPv4 Address", re.compile(
        r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    ), "<REDACTED_IP>"),

    # Generic high-entropy hex strings (32+ chars, often secrets)
    ("High-Entropy Hex String", re.compile(
        r'\b[a-fA-F0-9]{32,}\b'
    ), "<REDACTED_HEX_TOKEN>"),
]


def sanitize_log(text: str) -> tuple[str, SanitizationReport]:
    """Sanitize log text by removing sensitive information.

    Applies a series of regex-based redactions to strip API keys, tokens,
    passwords, database URIs, email addresses, IP addresses, and other
    potentially sensitive content from the input text.

    Args:
        text: Raw log text or stack trace to sanitize.

    Returns:
        Tuple of (sanitized_text, sanitization_report).
    """
    report = SanitizationReport(original_length=len(text))
    sanitized = text

    for pattern_name, pattern, replacement in _PATTERNS:
        matches = pattern.findall(sanitized)
        if matches:
            count = len(matches) if isinstance(matches[0], str) else len(matches)
            sanitized = pattern.sub(replacement, sanitized)
            report.redactions.append(
                f"{pattern_name}: {count} occurrence(s) redacted"
            )
            logger.debug("Redacted %d occurrence(s) of %s", count, pattern_name)

    # Sanitize home directory paths (platform-aware)
    home_pattern = re.compile(r'(/Users/|/home/|C:\\Users\\)[a-zA-Z0-9._-]+')
    home_matches = home_pattern.findall(sanitized)
    if home_matches:
        sanitized = home_pattern.sub(r'\1<REDACTED_USER>', sanitized)
        report.redactions.append(
            f"Home Directory Path: {len(home_matches)} occurrence(s) redacted"
        )

    report.sanitized_length = len(sanitized)

    if report.was_modified:
        logger.info(
            "Sanitization complete: %d redaction type(s) applied, "
            "text length %d -> %d",
            len(report.redactions), report.original_length, report.sanitized_length,
        )

    return sanitized, report


def sanitize_file_path(path: str) -> str:
    """Sanitize a file path by removing user-specific directory components.

    Args:
        path: A file path that may contain user-specific information.

    Returns:
        Sanitized file path.
    """
    sanitized = re.sub(
        r'(/Users/|/home/|C:\\Users\\)[a-zA-Z0-9._-]+', r'\1<USER>', path
    )
    return sanitized


def validate_no_secrets(text: str) -> list[str]:
    """Check if text contains potential secrets.

    This is a lightweight pre-flight check that can be used to warn
    users before any data is sent to an LLM.

    Args:
        text: Text to check for secrets.

    Returns:
        List of warning strings. Empty list means no secrets detected.
    """
    warnings = []
    for pattern_name, pattern, _ in _PATTERNS:
        if pattern.search(text):
            warnings.append(f"Potential {pattern_name} detected in input")
    return warnings
