"""Record real investigations and replay them offline.

A recording is the exact event stream of a live Gemini run (JSON lines with a
relative timestamp). Replay re-emits it with the original pacing, so the CLI and
web UI behave identically without an API key. Replays are labelled as such.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from pathlib import Path

RECORDINGS_DIR = Path(__file__).resolve().parent.parent / "recordings"
AUDIT_DIR = Path(__file__).resolve().parent.parent / "runs"  # git-ignored per-run audit trail
MAX_GAP_S = 4.0  # long model waits (quota retries) are shortened so a demo never stalls


def recording_path(incident_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]+", incident_id):
        raise ValueError(f"invalid incident id {incident_id!r}")
    return RECORDINGS_DIR / f"{incident_id}.jsonl"


def has_recording(incident_id: str) -> bool:
    return recording_path(incident_id).exists()


def audit_path(incident_id: str) -> Path:
    recording_path(incident_id)  # validates the id
    stamp = time.strftime("%Y%m%dT%H%M%S")
    return AUDIT_DIR / f"{stamp}-{incident_id}.jsonl"


async def record(events: AsyncIterator[dict], incident_id: str, dest: Path | None = None) -> AsyncIterator[dict]:
    """Pass events through unchanged while saving them; the file is only written if the run completes.

    Default destination is the replay recording; pass `dest=audit_path(id)` for an audit trail."""
    started, lines = time.monotonic(), []
    async for ev in events:
        lines.append(json.dumps({"at": round(time.monotonic() - started, 2), "event": ev}))
        yield ev
    dest = dest or recording_path(incident_id)
    dest.parent.mkdir(exist_ok=True)
    dest.write_text("\n".join(lines) + "\n")


async def replay(incident_id: str, speed: float = 1.0) -> AsyncIterator[dict]:
    """Yield a recorded run's events with their original pacing (gaps capped at MAX_GAP_S) divided by `speed`.

    Metrics inside the report event are the recorded live values, not the replay duration."""
    path = recording_path(incident_id)
    if not path.exists():
        raise FileNotFoundError(f"No recording for '{incident_id}'. Run `python -m ishikawa.eval` with a Gemini key first.")
    prev = 0.0
    for line in path.read_text().splitlines():
        item = json.loads(line)
        gap = min(item["at"] - prev, MAX_GAP_S) / speed
        prev = item["at"]
        if gap > 0:
            await asyncio.sleep(gap)
        ev = dict(item["event"])
        if ev["type"] in ("report", "done"):
            ev["replay"] = True
        yield ev
