"""SQLite storage. Each report and result belongs to one account."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.extract import LabRow
from app.facts import StoredResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    collected_on TEXT NOT NULL,
    panel_name TEXT NOT NULL,
    source_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    UNIQUE (user_id, collected_on, panel_name, source_name)
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    analyte TEXT NOT NULL,
    display_name TEXT NOT NULL,
    value REAL,
    value_text TEXT NOT NULL,
    unit TEXT NOT NULL,
    ref_low REAL,
    ref_high REAL,
    ref_text TEXT NOT NULL,
    flag TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    local_base_url TEXT NOT NULL,
    openai_api_key TEXT NOT NULL DEFAULT '',
    extraction_provider TEXT NOT NULL,
    extraction_model TEXT NOT NULL DEFAULT '',
    summary_provider TEXT NOT NULL,
    summary_model TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS summaries (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    fact_hash TEXT NOT NULL,
    model_label TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def open_db(path: Path):
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path: Path) -> None:
    with open_db(path) as conn:
        conn.executescript(SCHEMA)


def _as_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def create_user(path: Path, email: str, password_hash: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with open_db(path) as conn:
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, password_hash, now),
        )
        return int(cursor.lastrowid)


def user_by_email(path: Path, email: str) -> dict | None:
    with open_db(path) as conn:
        return _as_dict(
            conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        )


def user_by_id(path: Path, user_id: int) -> dict | None:
    with open_db(path) as conn:
        return _as_dict(
            conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        )


def insert_report(
    path: Path,
    user_id: int,
    collected_on: str,
    panel_name: str,
    source_name: str,
    stored_path: str,
    rows: list[LabRow],
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with open_db(path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO reports (
                user_id, collected_on, panel_name, source_name, stored_path, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, collected_on, panel_name, source_name, stored_path, now),
        )
        report_id = int(cursor.lastrowid)
        conn.executemany(
            """
            INSERT INTO results (
                report_id, user_id, analyte, display_name, value, value_text,
                unit, ref_low, ref_high, ref_text, flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    report_id,
                    user_id,
                    row.analyte,
                    row.display_name,
                    row.value,
                    row.value_text,
                    row.unit,
                    row.ref_low,
                    row.ref_high,
                    row.ref_text,
                    row.flag,
                )
                for row in rows
            ],
        )
        return report_id


def list_reports(path: Path, user_id: int) -> list[dict]:
    with open_db(path) as conn:
        return [
            _as_dict(row)
            for row in conn.execute(
                """
                SELECT reports.*, COUNT(results.id) AS result_count
                FROM reports
                LEFT JOIN results ON results.report_id = reports.id
                WHERE reports.user_id = ?
                GROUP BY reports.id
                ORDER BY reports.collected_on DESC, reports.id DESC
                """,
                (user_id,),
            )
        ]


def get_report(path: Path, user_id: int, report_id: int) -> dict | None:
    with open_db(path) as conn:
        return _as_dict(
            conn.execute(
                "SELECT * FROM reports WHERE id = ? AND user_id = ?",
                (report_id, user_id),
            ).fetchone()
        )


def results_for_report(path: Path, user_id: int, report_id: int) -> list[dict]:
    with open_db(path) as conn:
        return [
            _as_dict(row)
            for row in conn.execute(
                """
                SELECT * FROM results
                WHERE report_id = ? AND user_id = ?
                ORDER BY id
                """,
                (report_id, user_id),
            )
        ]


def get_llm_settings(path: Path, user_id: int) -> dict | None:
    with open_db(path) as conn:
        return _as_dict(
            conn.execute(
                "SELECT * FROM llm_settings WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        )


def save_llm_settings(path: Path, user_id: int, values: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with open_db(path) as conn:
        conn.execute(
            """
            INSERT INTO llm_settings (
                user_id, local_base_url, openai_api_key, extraction_provider,
                extraction_model, summary_provider, summary_model, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                local_base_url = excluded.local_base_url,
                openai_api_key = excluded.openai_api_key,
                extraction_provider = excluded.extraction_provider,
                extraction_model = excluded.extraction_model,
                summary_provider = excluded.summary_provider,
                summary_model = excluded.summary_model,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                values["local_base_url"],
                values["openai_api_key"],
                values["extraction_provider"],
                values["extraction_model"],
                values["summary_provider"],
                values["summary_model"],
                now,
            ),
        )


def get_summary(path: Path, user_id: int) -> dict | None:
    with open_db(path) as conn:
        return _as_dict(
            conn.execute(
                "SELECT * FROM summaries WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        )


def save_summary(path: Path, user_id: int, fact_hash: str, model_label: str, body: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with open_db(path) as conn:
        conn.execute(
            """
            INSERT INTO summaries (user_id, fact_hash, model_label, body, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                fact_hash = excluded.fact_hash,
                model_label = excluded.model_label,
                body = excluded.body,
                created_at = excluded.created_at
            """,
            (user_id, fact_hash, model_label, body, now),
        )


def results_for_user(path: Path, user_id: int) -> list[StoredResult]:
    with open_db(path) as conn:
        rows = conn.execute(
            """
            SELECT results.*, reports.collected_on
            FROM results
            JOIN reports ON reports.id = results.report_id
            WHERE results.user_id = ?
            ORDER BY reports.collected_on, results.id
            """,
            (user_id,),
        )
        return [
            StoredResult(
                collected_on=row["collected_on"],
                display_name=row["display_name"],
                analyte=row["analyte"],
                value=row["value"],
                value_text=row["value_text"],
                unit=row["unit"],
                ref_text=row["ref_text"],
                flag=row["flag"],
            )
            for row in rows
        ]
