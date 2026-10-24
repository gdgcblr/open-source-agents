"""SQLite usage log."""
from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager

DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "usage.db")


def _path(db_path: str | None) -> str:
    return db_path or os.getenv("TRACKER_DB_PATH", DEFAULT_DB)


@contextmanager
def connect(db_path: str | None = None):
    conn = sqlite3.connect(_path(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            source TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            thinking_tokens INTEGER NOT NULL DEFAULT 0,
            cached_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL NOT NULL,
            prompt_hash TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        """
    )
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def record(source, model, prompt_tokens, output_tokens, thinking_tokens,
           cached_tokens, cost_usd, prompt_hash=None, db_path=None, ts=None):
    with connect(db_path) as c:
        c.execute(
            "INSERT INTO usage (ts, source, model, prompt_tokens, output_tokens, "
            "thinking_tokens, cached_tokens, cost_usd, prompt_hash) VALUES (?,?,?,?,?,?,?,?,?)",
            (ts or time.time(), source, model, prompt_tokens, output_tokens,
             thinking_tokens, cached_tokens, cost_usd, prompt_hash),
        )


def rows_since(days: float, db_path=None) -> list[sqlite3.Row]:
    cutoff = time.time() - days * 86400
    with connect(db_path) as c:
        return c.execute("SELECT * FROM usage WHERE ts >= ? ORDER BY ts", (cutoff,)).fetchall()


def set_setting(key, value, db_path=None):
    with connect(db_path) as c:
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))


def get_setting(key, default=None, db_path=None):
    with connect(db_path) as c:
        row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default
