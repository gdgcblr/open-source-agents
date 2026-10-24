"""SQLite persistence, written after every turn.

Each turn commits the new state snapshot, the compiled briefing, the raw reply
and the reconciliation report in one transaction, so a process killed between
turns loses nothing that was finished. That is what makes ``resume`` real.

There is no column for a credential: worker configs are never stored.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from context_orchestration.contracts import (
    ContextPackage,
    ExecutionState,
    ReconciliationReport,
    WorkerConfig,
    now,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id    TEXT PRIMARY KEY,
    objective  TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS states (
    task_id    TEXT NOT NULL,
    turn       INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    saved_at   TEXT NOT NULL,
    PRIMARY KEY (task_id, turn)
);
CREATE TABLE IF NOT EXISTS turns (
    task_id        TEXT NOT NULL,
    turn           INTEGER NOT NULL,
    worker_id      TEXT NOT NULL,
    model          TEXT NOT NULL,
    assigned_task  TEXT NOT NULL,
    package_text   TEXT NOT NULL,
    package_tokens INTEGER NOT NULL,
    omitted_json   TEXT NOT NULL,
    raw_output     TEXT NOT NULL,
    report_json    TEXT NOT NULL,
    saved_at       TEXT NOT NULL,
    PRIMARY KEY (task_id, turn)
);
"""

DEFAULT_DB = "orchestration.db"


class SQLiteStore:
    def __init__(self, path: str | Path = DEFAULT_DB) -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    # -- writes ------------------------------------------------------------------

    def create(self, state: ExecutionState) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO tasks (task_id, objective, created_at) VALUES (?, ?, ?)",
                (state.task_id, state.objective, now()),
            )
            self._snapshot(state)

    def save_turn(
        self,
        state: ExecutionState,
        package: ContextPackage,
        raw_output: str,
        report: ReconciliationReport,
        worker: WorkerConfig,
    ) -> None:
        with self.conn:
            self._snapshot(state)
            self.conn.execute(
                "INSERT INTO turns VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    state.task_id, state.turn, worker.id, worker.model,
                    package.assigned_task, package.rendered_text, package.estimated_tokens,
                    json.dumps(package.omitted_sections), raw_output,
                    report.model_dump_json(), now(),
                ),
            )

    def _snapshot(self, state: ExecutionState) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO states VALUES (?, ?, ?, ?)",
            (state.task_id, state.turn, state.model_dump_json(), now()),
        )

    # -- reads -------------------------------------------------------------------

    def resolve(self, prefix: str) -> str:
        """A full task id from any unambiguous prefix."""
        rows = self.conn.execute(
            "SELECT task_id FROM tasks WHERE task_id LIKE ? ORDER BY task_id",
            (prefix.replace("%", "") + "%",),
        ).fetchall()
        if len(rows) != 1:
            raise KeyError(
                f"no task matches {prefix!r}" if not rows
                else f"{prefix!r} matches {len(rows)} tasks"
            )
        return rows[0]["task_id"]

    def load_state(self, task_id: str) -> ExecutionState | None:
        row = self.conn.execute(
            "SELECT state_json FROM states WHERE task_id = ? ORDER BY turn DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        return ExecutionState.model_validate_json(row["state_json"]) if row else None

    def turns(self, task_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM turns WHERE task_id = ? ORDER BY turn", (task_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def tasks(self) -> list[dict]:
        out = []
        for row in self.conn.execute("SELECT task_id, created_at FROM tasks ORDER BY created_at"):
            state = self.load_state(row["task_id"])
            if state:
                out.append({
                    "task_id": state.task_id,
                    "status": state.status,
                    "turn": state.turn,
                    "steps": len(state.plan),
                    "objective": state.objective,
                    "created_at": row["created_at"],
                })
        return out
