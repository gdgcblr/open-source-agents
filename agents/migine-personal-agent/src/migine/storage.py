import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_migrations VALUES(1);
CREATE TABLE IF NOT EXISTS sources(
 id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
 received TEXT NOT NULL, url TEXT NOT NULL, hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS records(
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
 payload TEXT NOT NULL, review TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS preferences(
 key TEXT PRIMARY KEY, value TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vectors(
 source_id TEXT PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
 model TEXT NOT NULL, vector TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS action_requests(
 id TEXT PRIMARY KEY, operation TEXT NOT NULL, payload TEXT NOT NULL,
 expires REAL NOT NULL, state TEXT NOT NULL, result TEXT);
CREATE TABLE IF NOT EXISTS audit_events(
 id INTEGER PRIMARY KEY, created TEXT NOT NULL, event TEXT NOT NULL, target TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sync_state(
 name TEXT PRIMARY KEY, updated TEXT NOT NULL, detail TEXT NOT NULL);
"""


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "migine.sqlite3"
        with self.connect() as db:
            db.executescript(SCHEMA)
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def audit(self, event: str, target: str):
        with self.connect() as db:
            db.execute(
                "INSERT INTO audit_events(created,event,target) VALUES(?,?,?)",
                (datetime.now(UTC).isoformat(), event, target),
            )

    def add_source(self, source: dict):
        digest = fingerprint(source)
        with self.connect() as db:
            existing = db.execute("SELECT hash FROM sources WHERE id=?", (source["id"],)).fetchone()
            if existing and existing["hash"] != digest:
                db.execute("DELETE FROM records WHERE source_id=?", (source["id"],))
                db.execute("DELETE FROM vectors WHERE source_id=?", (source["id"],))
            db.execute(
                "INSERT INTO sources VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "title=excluded.title,body=excluded.body,received=excluded.received,"
                "url=excluded.url,hash=excluded.hash",
                (
                    source["id"],
                    source["title"],
                    source["body"][:16000],
                    source["received"],
                    source["url"],
                    digest,
                ),
            )

    def add_record(self, source_id, record):
        payload = record.model_dump(mode="json")
        with self.connect() as db:
            source = db.execute("SELECT body FROM sources WHERE id=?", (source_id,)).fetchone()
            if not source or record.evidence not in source["body"]:
                raise ValueError("Evidence must be an exact passage from the source email.")
            key = fingerprint([source_id, payload])
            db.execute(
                "INSERT OR IGNORE INTO records(id,source_id,payload) VALUES(?,?,?)",
                (key, source_id, json.dumps(payload)),
            )
        return key

    def records(self, review="accepted"):
        with self.connect() as db:
            return [
                dict(r) | {"data": json.loads(r["payload"])}
                for r in db.execute(
                    "SELECT r.*,s.title,s.url FROM records r JOIN sources s ON s.id=r.source_id "
                    "WHERE r.review=? ORDER BY r.id",
                    (review,),
                )
            ]

    def review(self, key, accept):
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE records SET review=? WHERE id=? AND (review='pending' "
                "OR (review='accepted' AND ?=0))",
                ("accepted" if accept else "rejected", key, int(accept)),
            )
            if cursor.rowcount != 1:
                raise ValueError("Unknown or already reviewed record.")
        self.audit("record_accepted" if accept else "record_rejected", key)

    def remember(self, key, value):
        if not key or len(key) > 80 or len(value) > 2000:
            raise ValueError("Use a short memory key and value.")
        if key == "bill_notice_days" and (not value.isdigit() or not 0 <= int(value) <= 90):
            raise ValueError("bill_notice_days must be an integer from 0 to 90.")
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO preferences VALUES(?,?,?)",
                (key, value, datetime.now(UTC).isoformat()),
            )

    def forget_source(self, key):
        with self.connect() as db:
            db.execute("DELETE FROM sources WHERE id=?", (key,))
        self.audit("source_deleted", key)

    def coverage(self):
        with self.connect() as db:
            return {
                "cached_sources": db.execute("SELECT count(*) FROM sources").fetchone()[0],
                "pending_records": db.execute(
                    "SELECT count(*) FROM records WHERE review='pending'"
                ).fetchone()[0],
                "last_scans": [dict(r) for r in db.execute("SELECT * FROM sync_state")],
            }
