"""Load an ActivityLog from a JSON file.

Used by ``--test-mode`` and by the eval harness so the whole pipeline is
runnable offline with no GitHub token and no network, which keeps the project
reproducible on a clean machine (a repo contribution requirement).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .models import ActivityEvent, ActivityLog


def load_activity_log(path: str) -> ActivityLog:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    events = [
        ActivityEvent(
            event_id=e["event_id"],
            kind=e["kind"],
            repo=e.get("repo", "unknown/unknown"),
            title=e.get("title", ""),
            url=e.get("url", ""),
            timestamp=_parse_ts(e.get("timestamp")),
            state=e.get("state", ""),
            extra=e.get("extra", {}),
        )
        for e in data.get("events", [])
    ]
    return ActivityLog(
        username=data.get("username", "demo-user"),
        date=data.get("date", "2026-10-24"),
        events=events,
        fetch_warnings=data.get("fetch_warnings", []),
        partial=data.get("partial", False),
    )


def _parse_ts(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))
