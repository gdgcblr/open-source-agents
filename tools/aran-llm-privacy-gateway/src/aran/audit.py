"""Append-only audit log for DPDP-style accountability. Stores counts and hashes, never PII."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone

from aran.vault import aran_home


def _log_path():
    return aran_home() / "audit.jsonl"


def record(
    *,
    session_id: str,
    content: str,
    kind: str,
    profile: str,
    counts: dict[str, dict[str, int]],
    channel: str,
) -> dict:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session": session_id,
        "doc_sha256": hashlib.sha256(content.encode()).hexdigest()[:16],
        "kind": kind,
        "profile": profile,
        "channel": channel,
        "found": counts["found"],
        "masked": counts["masked"],
        "generalised": counts["generalised"],
        "kept": counts["kept"],
        "raw_values_sent": 0,
    }
    fd = os.open(_log_path(), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def record_event(*, session_id: str, event: str, types: list[str], channel: str) -> dict:
    """Guardrail events (e.g. a blocked request). Types only, never values."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session": session_id,
        "event": event,
        "types": sorted(set(types)),
        "channel": channel,
    }
    fd = os.open(_log_path(), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read(session_id: str | None = None, *, events: bool = False) -> list[dict]:
    """Redaction entries by default; guardrail events with events=True."""
    path = _log_path()
    if not path.exists():
        return []
    entries = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [
        e for e in entries
        if (session_id is None or e["session"] == session_id) and (("event" in e) == events)
    ]


def summarise(entries: list[dict]) -> dict:
    total: Counter[str] = Counter()
    masked: Counter[str] = Counter()
    for e in entries:
        total.update(e["found"])
        masked.update(e["masked"])
        masked.update(e["generalised"])
    return {
        "documents": len(entries),
        "pii_found": sum(total.values()),
        "pii_protected": sum(masked.values()),
        "by_type": dict(total.most_common()),
        "raw_values_sent": 0,
    }
