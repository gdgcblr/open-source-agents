import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    contact_name  TEXT NOT NULL,
    email         TEXT NOT NULL,
    language      TEXT NOT NULL CHECK (language IN ('en', 'hinglish')),
    flags         TEXT NOT NULL DEFAULT ''      -- ';'-separated, e.g. 'gentle;allow_final_notice'
);

CREATE TABLE IF NOT EXISTS invoices (
    id            TEXT PRIMARY KEY,             -- invoice number, e.g. INV-2026-001
    client_id     TEXT NOT NULL REFERENCES clients(id),
    currency      TEXT NOT NULL,
    amount_paise  INTEGER NOT NULL CHECK (amount_paise > 0),
    issue_date    TEXT NOT NULL,
    due_date      TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    hold          TEXT CHECK (hold IN ('DISPUTED', 'WRITTEN_OFF'))
);

CREATE TABLE IF NOT EXISTS payments (
    id            INTEGER PRIMARY KEY,
    txn_date      TEXT NOT NULL,
    amount_paise  INTEGER NOT NULL CHECK (amount_paise > 0),
    currency      TEXT NOT NULL,
    narration     TEXT NOT NULL,
    ref           TEXT NOT NULL DEFAULT '',
    dedupe_key    TEXT NOT NULL UNIQUE,
    status        TEXT NOT NULL DEFAULT 'UNMATCHED'
                  CHECK (status IN ('UNMATCHED', 'PENDING_CONFIRMATION', 'MATCHED'))
);

CREATE TABLE IF NOT EXISTS match_proposals (
    id              INTEGER PRIMARY KEY,
    payment_id      INTEGER NOT NULL REFERENCES payments(id),
    invoice_ids     TEXT NOT NULL,              -- JSON list
    signal          TEXT NOT NULL,
    name_confidence REAL NOT NULL,
    reason          TEXT NOT NULL,
    decision        TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('APPLIED', 'PENDING', 'REJECTED', 'SUPERSEDED')),
    ambiguous_with  TEXT NOT NULL DEFAULT '[]',
    run_id          TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS allocations (
    id            INTEGER PRIMARY KEY,
    payment_id    INTEGER NOT NULL REFERENCES payments(id),
    invoice_id    TEXT NOT NULL REFERENCES invoices(id),
    paid_paise    INTEGER NOT NULL CHECK (paid_paise >= 0),
    tds_paise     INTEGER NOT NULL DEFAULT 0 CHECK (tds_paise >= 0),
    proposal_id   INTEGER REFERENCES match_proposals(id),
    applied_by    TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id               INTEGER PRIMARY KEY,
    invoice_id       TEXT NOT NULL REFERENCES invoices(id),
    tone_level       INTEGER NOT NULL CHECK (tone_level BETWEEN 0 AND 3),
    language         TEXT NOT NULL,
    subject          TEXT NOT NULL DEFAULT '',
    body             TEXT NOT NULL DEFAULT '',
    amount_due_paise INTEGER NOT NULL,
    status           TEXT NOT NULL,
    reasons          TEXT NOT NULL DEFAULT '[]', -- JSON list (policy reasons when DROPPED)
    edited_by_owner  INTEGER NOT NULL DEFAULT 0,
    run_id           TEXT,
    created_at       TEXT NOT NULL,
    sent_on          TEXT
);

CREATE TABLE IF NOT EXISTS audit (
    id         INTEGER PRIMARY KEY,
    ts         TEXT NOT NULL,
    run_id     TEXT,
    actor      TEXT NOT NULL,
    action     TEXT NOT NULL,
    entity     TEXT NOT NULL,
    entity_id  TEXT NOT NULL,
    details    TEXT NOT NULL DEFAULT '{}'
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
