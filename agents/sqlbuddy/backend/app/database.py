"""Small SQLite repository for saved sessions and question history."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4


class HistoryStore:
    """Persist only SQLBuddy's app history, using parameterized SQL throughout."""

    def __init__(self, database_path: str):
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        """Create or upgrade the initial schema; version 1 is the current schema."""
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, dialect TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    question TEXT NOT NULL, answer_json TEXT NOT NULL,
                    dialect TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_session_idx ON messages(session_id, id);
                """
            )
            row = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
            if row is None:
                connection.execute("INSERT INTO schema_version(version) VALUES (1)")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def add_message(
        self, session_id: UUID | None, question: str, answer: dict[str, Any], dialect: str
    ) -> tuple[UUID, str]:
        """Create a session when needed and save a question and its answer."""
        now = self._now()
        is_new = session_id is None
        session_id = session_id or uuid4()
        with self._connect() as connection:
            if not is_new and connection.execute(
                "SELECT 1 FROM sessions WHERE id = ?", (str(session_id),)
            ).fetchone() is None:
                raise KeyError("Session not found.")
            if is_new:
                title = question[:80].strip() or "New SQL question"
                connection.execute(
                    "INSERT INTO sessions(id, title, dialect, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (str(session_id), title, dialect, now, now),
                )
            else:
                connection.execute(
                    "UPDATE sessions SET dialect = ?, updated_at = ? WHERE id = ?",
                    (dialect, now, str(session_id)),
                )
            connection.execute(
                "INSERT INTO messages(session_id, question, answer_json, dialect, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(session_id), question, json.dumps(answer), dialect, now),
            )
        return session_id, now

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, title, dialect, updated_at FROM sessions ORDER BY updated_at DESC LIMIT 200"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, session_id: UUID) -> dict[str, Any] | None:
        with self._connect() as connection:
            session = connection.execute(
                "SELECT id, title, dialect, updated_at FROM sessions WHERE id = ?",
                (str(session_id),),
            ).fetchone()
            if session is None:
                return None
            messages = connection.execute(
                "SELECT question, answer_json, dialect, created_at FROM messages WHERE session_id = ? ORDER BY id",
                (str(session_id),),
            ).fetchall()
        result = dict(session)
        result["messages"] = [
            {"question": row["question"], "answer": json.loads(row["answer_json"]),
             "dialect": row["dialect"], "created_at": row["created_at"]}
            for row in messages
        ]
        return result

    def rename_session(self, session_id: UUID, title: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title, self._now(), str(session_id)),
            )
        return cursor.rowcount > 0

    def delete_session(self, session_id: UUID) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM sessions WHERE id = ?", (str(session_id),))
        return cursor.rowcount > 0

    def check(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False
