"""Small local SQLite memory for searchable, non-authoritative past cases."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .policy import tokens

MAX_CASES = 10_000
MAX_MEMORY_QUERY_LENGTH = 2000


class CaseMemory:
    available = True

    def __init__(self, database_path: Path) -> None:
        database_path = Path(database_path)
        if str(database_path) != ":memory:":
            if database_path.is_symlink():
                raise ValueError("Case memory database must not be a symbolic link.")
            database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.connection = sqlite3.connect(database_path, timeout=5)
        if str(database_path) != ":memory:":
            os.chmod(database_path, 0o600)
        self.connection.execute("PRAGMA busy_timeout = 5000")
        if str(database_path) != ":memory:":
            self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                policy_ids TEXT NOT NULL
            )
            """
        )
        self.connection.commit()
        if str(database_path) != ":memory:":
            os.chmod(database_path, 0o600)

    def remember(self, result: dict[str, Any]) -> None:
        if (
            not isinstance(result.get("case_id"), str)
            or not result["case_id"]
            or len(result["case_id"]) > 128
            or not isinstance(result.get("request_summary"), str)
            or len(result["request_summary"]) > MAX_MEMORY_QUERY_LENGTH
            or not isinstance(result.get("recommendation"), str)
            or result["recommendation"] not in {"approve", "deny", "escalate"}
            or not isinstance(result.get("policy_citations"), list)
            or not all(isinstance(item, str) and len(item) <= 128
                       for item in result["policy_citations"])
        ):
            raise ValueError("Invalid case record for memory.")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self.connection.execute(
                "SELECT 1 FROM cases WHERE case_id = ?", (result["case_id"],)
            ).fetchone()
            count = self.connection.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
            if existing is None and count >= MAX_CASES:
                raise ValueError("Case memory reached its 10,000-record limit.")
            self.connection.execute(
                """
                INSERT OR REPLACE INTO cases (case_id, summary, recommendation, policy_ids)
                VALUES (?, ?, ?, ?)
                """,
                (
                    result["case_id"],
                    result["request_summary"],
                    result["recommendation"],
                    json.dumps(result["policy_citations"]),
                ),
            )
            self.connection.commit()
        except (sqlite3.Error, ValueError):
            self.connection.rollback()
            raise

    def search(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        if not isinstance(query, str) or len(query) > MAX_MEMORY_QUERY_LENGTH:
            raise ValueError("Memory search query must be a string of at most 2000 chars.")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
            raise ValueError("Memory search limit must be an integer from 1 to 20.")
        query_tokens = tokens(query)
        if not query_tokens:
            return []
        rows = self.connection.execute(
            "SELECT case_id, summary, recommendation, policy_ids FROM cases"
        ).fetchall()
        scored = []
        for case_id, summary, recommendation, policy_ids in rows:
            overlap = len(query_tokens & tokens(summary))
            if overlap:
                scored.append(
                    (
                        overlap,
                        case_id,
                        {
                            "case_id": case_id,
                            "summary": summary,
                            "recommendation": recommendation,
                            "policy_ids": json.loads(policy_ids),
                        },
                    )
                )
        scored.sort(key=lambda row: (-row[0], row[1]))
        return [case for _, _, case in scored[:limit]]

    def forget(self, case_id: str | None = None, all_cases: bool = False) -> int:
        if all_cases:
            cursor = self.connection.execute("DELETE FROM cases")
        elif isinstance(case_id, str) and case_id:
            cursor = self.connection.execute(
                "DELETE FROM cases WHERE case_id = ?", (case_id,)
            )
        else:
            raise ValueError("Provide a case ID or explicitly request all-case deletion.")
        self.connection.commit()
        return cursor.rowcount

    def close(self) -> None:
        self.connection.close()


class UnavailableCaseMemory:
    """Explicit no-op adapter used only when optional local memory cannot open."""

    available = False

    def __init__(self, error_type: str) -> None:
        self.error_type = error_type

    def search(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        raise sqlite3.OperationalError("Case memory is unavailable.")

    def remember(self, result: dict[str, Any]) -> None:
        raise sqlite3.OperationalError("Case memory is unavailable.")

    def close(self) -> None:
        return None


def open_case_memory(database_path: Path) -> CaseMemory | UnavailableCaseMemory:
    try:
        return CaseMemory(database_path)
    except (OSError, sqlite3.Error) as error:
        return UnavailableCaseMemory(type(error).__name__)
