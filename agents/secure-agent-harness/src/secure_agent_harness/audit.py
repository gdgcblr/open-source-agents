"""Minimal structured audit; deliberately avoids storing raw prompts/tool arguments."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
]


def redact(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result[:500]


class AuditLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, name: str, **metadata: Any) -> None:
        # Callers should pass metadata only, never full prompts or credentials.
        safe_metadata = {
            str(k)[:64]: redact(str(v))[:300]
            for k, v in metadata.items()
            if k.lower() not in {"prompt", "messages", "api_key", "password", "secret", "arguments"}
        }
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": name,
            "metadata": safe_metadata,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
