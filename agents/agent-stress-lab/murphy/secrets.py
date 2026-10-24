"""Redaction for anything written to traces and reports."""

from __future__ import annotations

import re
from typing import Any

SECRET_KEY = re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|authorization|credential)")
# Vendor-shaped secrets only: a generic "long base64" rule also masked ordinary IDs and hashes.
SECRET_VALUE = re.compile(r"\b(sk-[A-Za-z0-9_-]{12,}|AIza[0-9A-Za-z_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abprs]-[A-Za-z0-9-]{10,})\b")
MASK = "***"


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (MASK if isinstance(k, str) and SECRET_KEY.search(k) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return SECRET_VALUE.sub(MASK, value)
    return value
