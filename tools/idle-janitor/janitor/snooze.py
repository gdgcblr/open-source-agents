"""Snooze state — remember which resources the user asked us to ignore for a bit.

Stored in ~/.idle-janitor/snooze.json so it survives restarts without needing
a database. Format: { "<resource_id>": <unix_timestamp_until> }.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

STATE_DIR = Path.home() / ".idle-janitor"
STATE_FILE = STATE_DIR / "snooze.json"


def _load() -> dict[str, float]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save(state: dict[str, float]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def is_snoozed(resource_id: str) -> bool:
    state = _load()
    until = state.get(resource_id)
    if until is None:
        return False
    if time.time() >= until:
        # Expired — clean up lazily.
        state.pop(resource_id, None)
        _save(state)
        return False
    return True


def snooze(resource_id: str, minutes: int) -> float:
    """Snooze a resource for N minutes. Returns the expiry timestamp."""
    state = _load()
    until = time.time() + max(1, minutes) * 60
    state[resource_id] = until
    _save(state)
    return until


def clear(resource_id: str) -> bool:
    state = _load()
    if resource_id in state:
        state.pop(resource_id)
        _save(state)
        return True
    return False


def list_snoozed() -> dict[str, float]:
    """Returns {resource_id: seconds_remaining} for all active snoozes."""
    state = _load()
    now = time.time()
    return {rid: max(0, int(until - now)) for rid, until in state.items() if until > now}
