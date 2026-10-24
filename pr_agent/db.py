"""SQLite persistence: repos, PRs, runs (job queue) and the audit/event log."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    full_name TEXT PRIMARY KEY,
    status TEXT DEFAULT 'idle',
    last_polled_at TEXT,
    last_error TEXT
);
CREATE TABLE IF NOT EXISTS prs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    number INTEGER NOT NULL,
    title TEXT, author TEXT, url TEXT, body TEXT,
    head_sha TEXT, base_ref TEXT, head_ref TEXT,
    state TEXT, draft INTEGER DEFAULT 0, gh_updated_at TEXT,
    status TEXT DEFAULT 'new',
    evaluated_sha TEXT, approved_sha TEXT,
    category TEXT, recommendation TEXT, risk TEXT,
    value_score REAL, quality_score REAL,
    evaluation_json TEXT,
    updated_at TEXT,
    UNIQUE(repo, number)
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    sha TEXT,
    status TEXT DEFAULT 'queued',
    created_at TEXT, started_at TEXT, finished_at TEXT,
    workspace TEXT, report_json TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, pr_id INTEGER, run_id INTEGER,
    level TEXT, message TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)

    def q(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        rows = self.q(sql, params)
        return rows[0] if rows else None

    def exec(self, sql: str, params: tuple = ()) -> int:
        with self._lock:
            return self._conn.execute(sql, params).lastrowid

    # ---- events / audit log
    def log(self, message: str, pr_id: int | None = None, run_id: int | None = None, level: str = "info") -> None:
        self.exec("INSERT INTO events(ts, pr_id, run_id, level, message) VALUES (?,?,?,?,?)",
                  (now(), pr_id, run_id, level, message[:4000]))

    # ---- repos
    def upsert_repo(self, name: str, status: str, error: str | None = None) -> None:
        self.exec("""INSERT INTO repos(full_name, status, last_polled_at, last_error) VALUES (?,?,?,?)
                     ON CONFLICT(full_name) DO UPDATE SET status=excluded.status,
                     last_polled_at=excluded.last_polled_at, last_error=excluded.last_error""",
                  (name, status, now(), error))

    # ---- PRs
    def upsert_pr(self, repo: str, pr: dict) -> tuple[int, bool]:
        """Insert or refresh a PR. Returns (pr_id, revision_changed)."""
        existing = self.one("SELECT * FROM prs WHERE repo=? AND number=?", (repo, pr["number"]))
        fields = (pr["title"], pr["user"]["login"], pr["html_url"], (pr.get("body") or "")[:8000],
                  pr["head"]["sha"], pr["base"]["ref"], pr["head"]["ref"], pr["state"],
                  int(bool(pr.get("draft"))), pr["updated_at"], now())
        if existing is None:
            pr_id = self.exec("""INSERT INTO prs(title, author, url, body, head_sha, base_ref, head_ref, state,
                                 draft, gh_updated_at, updated_at, repo, number) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                              fields + (repo, pr["number"]))
            return pr_id, True
        self.exec("""UPDATE prs SET title=?, author=?, url=?, body=?, head_sha=?, base_ref=?, head_ref=?, state=?,
                     draft=?, gh_updated_at=?, updated_at=? WHERE id=?""", fields + (existing["id"],))
        return existing["id"], existing["head_sha"] != pr["head"]["sha"]

    def get_pr(self, pr_id: int) -> dict | None:
        pr = self.one("SELECT * FROM prs WHERE id=?", (pr_id,))
        if pr and pr.get("evaluation_json"):
            pr["evaluation"] = json.loads(pr["evaluation_json"])
        return pr

    def set_pr(self, pr_id: int, **fields: Any) -> None:
        fields["updated_at"] = now()
        cols = ", ".join(f"{k}=?" for k in fields)
        self.exec(f"UPDATE prs SET {cols} WHERE id=?", tuple(fields.values()) + (pr_id,))

    # ---- runs (job queue)
    def enqueue(self, pr_id: int, kind: str, sha: str) -> int | None:
        """Queue a run unless the same kind is already queued/running for this exact revision."""
        dup = self.one("SELECT id FROM runs WHERE pr_id=? AND kind=? AND sha=? AND status IN ('queued','running')",
                       (pr_id, kind, sha))
        if dup:
            return None
        return self.exec("INSERT INTO runs(pr_id, kind, sha, status, created_at) VALUES (?,?,?,'queued',?)",
                         (pr_id, kind, sha, now()))

    def next_run(self) -> dict | None:
        with self._lock:
            run = self.one("SELECT * FROM runs WHERE status='queued' ORDER BY id LIMIT 1")
            if run:
                self.exec("UPDATE runs SET status='running', started_at=? WHERE id=?", (now(), run["id"]))
            return run

    def finish_run(self, run_id: int, status: str, report: dict | None = None, error: str | None = None) -> None:
        self.exec("UPDATE runs SET status=?, finished_at=?, report_json=?, error=? WHERE id=?",
                  (status, now(), json.dumps(report) if report is not None else None, error, run_id))

    def recover(self) -> int:
        """After a restart, runs left 'running' were interrupted mid-flight. Mark them so; never resume blindly."""
        stuck = self.q("SELECT id, pr_id, kind FROM runs WHERE status='running'")
        for r in stuck:
            self.finish_run(r["id"], "interrupted", error="Process stopped while this run was in progress.")
            new_status = "new" if r["kind"] == "evaluate" else "interrupted"
            self.set_pr(r["pr_id"], status=new_status)
            self.log("Run interrupted by a restart; marked as interrupted.", r["pr_id"], r["id"], "warn")
        return len(stuck)
