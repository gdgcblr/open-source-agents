"""Persistent waste journal — one SQLite row per observed resource per scan.

Lets us answer *"how much have I wasted this week?"* without keeping anything
in memory and without any external services. The DB lives at
~/.idle-janitor/history.db.

We write a lightweight snapshot every time list_idle_resources /
estimate_waste is called, so the dashboard and CLI naturally keep the journal
warm during a demo. A dedicated 'record_snapshot' entry point is also exposed
so a watcher loop can log independently of any client call.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

DB_DIR = Path.home() / ".idle-janitor"
DB_FILE = DB_DIR / "history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    ts            REAL    NOT NULL,
    resource_id   TEXT    NOT NULL,
    name          TEXT,
    kind          TEXT    NOT NULL,
    uptime_s      INTEGER NOT NULL,
    cpu_percent   REAL    NOT NULL,
    mem_mb        REAL    NOT NULL,
    watts         REAL    NOT NULL,
    wh            REAL    NOT NULL,
    inr           REAL    NOT NULL,
    co2_g         REAL    NOT NULL,
    idle          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);
CREATE INDEX IF NOT EXISTS idx_snapshots_rid ON snapshots(resource_id);

CREATE TABLE IF NOT EXISTS reap_log (
    ts            REAL    NOT NULL,
    resource_id   TEXT    NOT NULL,
    name          TEXT,
    kind          TEXT    NOT NULL,
    dry_run       INTEGER NOT NULL,
    wh_at_reap    REAL,
    inr_at_reap   REAL,
    co2_g_at_reap REAL,
    reason        TEXT
);
CREATE INDEX IF NOT EXISTS idx_reap_ts ON reap_log(ts);
"""


@contextmanager
def _conn():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def record_snapshot(resources: Iterable[dict]) -> int:
    """Insert one row per resource. Returns the number of rows written."""
    now = time.time()
    rows = [
        (
            now,
            r.get("id", ""),
            r.get("name", ""),
            r.get("kind", "unknown"),
            int(r.get("uptime_seconds", 0)),
            float(r.get("cpu_percent", 0.0)),
            float(r.get("mem_mb", 0.0)),
            float(r.get("estimated_watts", 0.0)),
            float(r.get("wh", 0.0)),
            float(r.get("inr", 0.0)),
            float(r.get("co2_g", 0.0)),
            1 if r.get("idle") else 0,
        )
        for r in resources
    ]
    if not rows:
        return 0
    with _conn() as conn:
        conn.executemany(
            "INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows
        )
    return len(rows)


def record_reap(resource: dict, dry_run: bool, reason: str = "") -> None:
    """Journal every (attempted) reap for the audit trail."""
    with _conn() as conn:
        conn.execute(
            "INSERT INTO reap_log VALUES (?,?,?,?,?,?,?,?,?)",
            (
                time.time(),
                resource.get("id", ""),
                resource.get("name", ""),
                resource.get("kind", "unknown"),
                1 if dry_run else 0,
                float(resource.get("wh", 0.0)) if resource.get("wh") is not None else None,
                float(resource.get("inr", 0.0)) if resource.get("inr") is not None else None,
                float(resource.get("co2_g", 0.0)) if resource.get("co2_g") is not None else None,
                reason,
            ),
        )


def _window_seconds(window: str) -> float:
    """Parse '7d', '24h', '30m', '3600' into seconds."""
    window = (window or "").strip().lower()
    if not window:
        return 7 * 86400
    try:
        if window.endswith("d"):
            return float(window[:-1]) * 86400
        if window.endswith("h"):
            return float(window[:-1]) * 3600
        if window.endswith("m"):
            return float(window[:-1]) * 60
        return float(window)
    except ValueError:
        return 7 * 86400


def summarize_window(window: str = "7d") -> dict[str, Any]:
    """Aggregate waste across a time window.

    For each resource_id we keep the MAX wh/inr/co2 observed (since those are
    cumulative since the resource started), then sum those maxes. This correctly
    attributes 'total waste over the window' without double-counting.
    """
    since = time.time() - _window_seconds(window)
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT resource_id,
                   MAX(name)              AS name,
                   MAX(kind)              AS kind,
                   MAX(wh)                AS wh,
                   MAX(inr)               AS inr,
                   MAX(co2_g)             AS co2_g,
                   MAX(uptime_s)          AS uptime_s,
                   COUNT(*)               AS samples,
                   MIN(ts)                AS first_seen,
                   MAX(ts)                AS last_seen
            FROM snapshots
            WHERE ts >= ?
            GROUP BY resource_id
            ORDER BY wh DESC
            """,
            (since,),
        ).fetchall()

    per_resource = [
        {
            "resource_id": r[0],
            "name": r[1],
            "kind": r[2],
            "wh": round(r[3], 2),
            "inr": round(r[4], 2),
            "co2_g": round(r[5], 2),
            "uptime_s": r[6],
            "samples": r[7],
            "first_seen": r[8],
            "last_seen": r[9],
        }
        for r in rows
    ]
    total_wh = sum(r["wh"] for r in per_resource)
    total_inr = sum(r["inr"] for r in per_resource)
    total_co2_g = sum(r["co2_g"] for r in per_resource)

    return {
        "window": window,
        "resource_count": len(per_resource),
        "total_wh": round(total_wh, 2),
        "total_inr": round(total_inr, 2),
        "total_co2_g": round(total_co2_g, 2),
        "resources": per_resource,
    }


def reap_history(window: str = "7d") -> list[dict[str, Any]]:
    since = time.time() - _window_seconds(window)
    with _conn() as conn:
        rows = conn.execute(
            "SELECT ts, resource_id, name, kind, dry_run, wh_at_reap, inr_at_reap, co2_g_at_reap, reason "
            "FROM reap_log WHERE ts >= ? ORDER BY ts DESC",
            (since,),
        ).fetchall()
    return [
        {
            "ts": r[0],
            "resource_id": r[1],
            "name": r[2],
            "kind": r[3],
            "dry_run": bool(r[4]),
            "wh": r[5],
            "inr": r[6],
            "co2_g": r[7],
            "reason": r[8],
        }
        for r in rows
    ]
