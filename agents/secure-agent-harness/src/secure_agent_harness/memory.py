"""Small SQLite memory store with mandatory namespace isolation."""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


class MemoryStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_user ON facts(user_id, id DESC)")

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def remember(self, user_id: str, fact: str) -> None:
        fact = fact.strip()
        if not user_id or len(user_id) > 128:
            raise ValueError("Invalid user namespace")
        if not fact or len(fact) > 500:
            raise ValueError("Fact must be 1-500 characters")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO facts(user_id, fact, created_at) VALUES (?, ?, ?)",
                (user_id, fact, datetime.now(timezone.utc).isoformat()),
            )
            # Retain only the most recent 100 facts for each namespace.
            conn.execute("""
                DELETE FROM facts
                WHERE user_id = ? AND id NOT IN (
                    SELECT id FROM facts WHERE user_id = ? ORDER BY id DESC LIMIT 100
                )
            """, (user_id, user_id))

    def recent(self, user_id: str, limit: int = 8) -> list[str]:
        limit = max(1, min(int(limit), 20))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT fact FROM facts WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [row[0] for row in rows]

    def clear(self, user_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM facts WHERE user_id = ?", (user_id,))
