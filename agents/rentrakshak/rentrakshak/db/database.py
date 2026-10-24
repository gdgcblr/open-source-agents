from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from rentrakshak.config import default_db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL UNIQUE,
    edit_token TEXT NOT NULL,
    locality TEXT NOT NULL,
    property_type TEXT NOT NULL,
    rent_band TEXT,
    category TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    experience_text TEXT NOT NULL,
    move_period TEXT,
    rating_maintenance INTEGER,
    rating_communication INTEGER,
    moderation_status TEXT NOT NULL DEFAULT 'pending_review',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS vacating_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL UNIQUE,
    edit_token TEXT NOT NULL,
    locality TEXT NOT NULL,
    property_type TEXT NOT NULL,
    room_type TEXT NOT NULL,
    monthly_rent_inr INTEGER NOT NULL,
    deposit_inr INTEGER,
    availability_date TEXT NOT NULL,
    furnishing TEXT,
    maintenance_inr INTEGER,
    post_kind TEXT NOT NULL,
    description TEXT NOT NULL,
    viewing_windows TEXT,
    contact_method_private TEXT NOT NULL,
    owner_permission_ack INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS moderation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_type TEXT NOT NULL,
    content_public_id TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS content_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_type TEXT NOT NULL,
    content_public_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_exp_locality ON experiences(locality);
CREATE INDEX IF NOT EXISTS idx_exp_status ON experiences(moderation_status);
CREATE INDEX IF NOT EXISTS idx_vac_status ON vacating_posts(status);
CREATE INDEX IF NOT EXISTS idx_vac_locality ON vacating_posts(locality);
"""


def init_db(db_path: Path | None = None) -> Path:
    path = db_path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()
    return path


@contextmanager
def get_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = db_path or default_db_path()
    init_db(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
