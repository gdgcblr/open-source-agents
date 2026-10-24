"""Execution history and audit logging for DevGuard."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devguard.redact import redact_secrets


DEFAULT_HISTORY_FILE = Path(".devguard") / "history.jsonl"
MAX_HISTORY_LINES = 1000
MAX_OUTPUT_SNIPPET_CHARS = 2048


@dataclass
class AuditRecord:
    """Structured audit record for a command evaluation and execution."""
    timestamp: str
    command: list[str]
    executable: str
    working_dir: str
    decision: str
    approval_status: str
    matched_rule: list[str] | None
    exit_code: int | None
    duration_ms: float | None
    output_snippet: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_default_history_path() -> Path:
    """Return default audit history file path, falling back to home dir if needed."""
    local_dir = Path(".devguard")
    try:
        local_dir.mkdir(parents=True, exist_ok=True)
        return local_dir / "history.jsonl"
    except OSError:
        home_dir = Path.home() / ".devguard"
        home_dir.mkdir(parents=True, exist_ok=True)
        return home_dir / "history.jsonl"


def record_audit(
    command: list[str],
    executable: str,
    decision: str,
    approval_status: str,
    matched_rule: tuple[str, ...] | None = None,
    exit_code: int | None = None,
    duration_ms: float | None = None,
    raw_output: str = "",
    history_path: Path | None = None,
) -> AuditRecord:
    """Create, redact, and persist an audit record to disk.

    Args:
        command: Full command argument list.
        executable: Effective executable name.
        decision: Evaluated policy decision ('allow', 'ask', 'deny').
        approval_status: User approval outcome ('approved', 'rejected', 'not_required', 'non_interactive_blocked').
        matched_rule: The rule tuple that matched, if any.
        exit_code: Subprocess exit code, or None if command was blocked.
        duration_ms: Execution duration in milliseconds.
        raw_output: Command output before redaction and truncation.
        history_path: Optional explicit history file path.

    Returns:
        The persisted AuditRecord object.
    """
    path = history_path or get_default_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Sanitize and redact command tokens
    sanitized_command = [redact_secrets(arg) for arg in command]

    # Sanitize and truncate output snippet
    snippet = raw_output[:MAX_OUTPUT_SNIPPET_CHARS] if raw_output else ""
    redacted_snippet = redact_secrets(snippet)
    if len(raw_output) > MAX_OUTPUT_SNIPPET_CHARS:
        redacted_snippet += "\n... [audit output truncated] ..."

    record = AuditRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        command=sanitized_command,
        executable=executable,
        working_dir=str(Path.cwd()),
        decision=decision.upper(),
        approval_status=approval_status,
        matched_rule=list(matched_rule) if matched_rule else None,
        exit_code=exit_code,
        duration_ms=round(duration_ms, 2) if duration_ms is not None else None,
        output_snippet=redacted_snippet,
    )

    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict()) + "\n")
    except OSError:
        pass

    # Prune history if file exceeds maximum line limit
    _prune_history_if_needed(path)

    return record


def _prune_history_if_needed(path: Path) -> None:
    """Maintain history size by retaining the most recent records."""
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_HISTORY_LINES:
            # Retain the most recent half
            keep = lines[-(MAX_HISTORY_LINES // 2):]
            path.write_text("\n".join(keep) + "\n", encoding="utf-8")
    except OSError:
        pass


def get_audit_history(limit: int = 20, history_path: Path | None = None) -> list[dict[str, Any]]:
    """Retrieve the most recent audit records from the history log.

    Args:
        limit: Maximum number of records to return.
        history_path: Optional explicit history file path.

    Returns:
        List of audit record dicts, newest first.
    """
    path = history_path or get_default_history_path()
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    try:
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
                if len(records) >= limit:
                    break
            except json.JSONDecodeError:
                continue
    except OSError:
        return []

    return records

