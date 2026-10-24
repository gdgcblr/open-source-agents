"""Small, local privacy helpers for resident-authored civic reports."""

from __future__ import annotations

import re

PATTERNS = {
    "phone": re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)(?!\d)"),
    "email": re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
}


def find_sensitive_data(*values: str) -> list[str]:
    """Return detected data classes without returning the sensitive values."""
    combined = " ".join(value or "" for value in values)
    return [name for name, pattern in PATTERNS.items() if pattern.search(combined)]


def redact_text(value: str) -> str:
    """Create a review-safe preview; the original remains untouched in the UI."""
    redacted = PATTERNS["email"].sub("[email removed]", value or "")
    return PATTERNS["phone"].sub("[phone removed]", redacted)
