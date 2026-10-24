"""
RepoLens — PostgreSQL Database Layer

Uses psycopg3 (psycopg) with parameterized queries throughout.
No ORM. No migration framework.
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Any, Generator, Optional

try:
    import psycopg
    from psycopg.rows import dict_row
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False

from backend.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _get_connection():
    """Open a single psycopg3 connection. Caller must close."""
    if not PSYCOPG_AVAILABLE:
        raise RuntimeError("psycopg3 is not installed. Run: pip install psycopg[binary]")
    settings = get_settings()
    return psycopg.connect(settings.database_url, row_factory=dict_row)


@contextmanager
def get_db() -> Generator:
    """Context manager that yields a connection and commits/rolls back."""
    conn = _get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------

def init_schema(schema_path: str = "db/schema.sql") -> None:
    """Execute the schema SQL file. Safe to run multiple times (IF NOT EXISTS)."""
    try:
        with open(schema_path) as f:
            sql = f.read()
        with get_db() as conn:
            conn.execute(sql)
        logger.info("Database schema initialized from %s", schema_path)
    except Exception as exc:
        logger.error("Schema initialization failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# CRUD operations — all use parameterized queries
# ---------------------------------------------------------------------------

def upsert_audit(
    *,
    repository_url: str,
    repository_name: str,
    commit_sha: Optional[str],
    scan_status: str,
    is_demo: bool,
    report_json: Optional[dict],
    report_markdown: Optional[str],
    scanner_status: Optional[dict],
) -> int:
    """
    Insert a new audit or update the existing record for this URL.
    Returns the row id.
    """
    with get_db() as conn:
        row = conn.execute(
            """
            INSERT INTO repository_audits
                (repository_url, repository_name, commit_sha, scan_status,
                 is_demo, report_json, report_markdown, scanner_status)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)
            ON CONFLICT (repository_url) DO UPDATE SET
                repository_name = EXCLUDED.repository_name,
                commit_sha      = EXCLUDED.commit_sha,
                scan_status     = EXCLUDED.scan_status,
                is_demo         = EXCLUDED.is_demo,
                report_json     = EXCLUDED.report_json,
                report_markdown = EXCLUDED.report_markdown,
                scanner_status  = EXCLUDED.scanner_status,
                updated_at      = NOW()
            RETURNING id
            """,
            (
                repository_url,
                repository_name,
                commit_sha,
                scan_status,
                is_demo,
                json.dumps(report_json) if report_json is not None else None,
                report_markdown,
                json.dumps(scanner_status) if scanner_status is not None else None,
            ),
        ).fetchone()
    return row["id"]  # type: ignore[index]


def update_scan_status(audit_id: int, status: str) -> None:
    """Update only the scan_status field for a given audit."""
    with get_db() as conn:
        conn.execute(
            "UPDATE repository_audits SET scan_status = %s WHERE id = %s",
            (status, audit_id),
        )


def get_audit_by_id(audit_id: int) -> Optional[dict[str, Any]]:
    """Fetch one audit row by primary key."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM repository_audits WHERE id = %s",
            (audit_id,),
        ).fetchone()


def get_audit_by_url(url: str) -> Optional[dict[str, Any]]:
    """Fetch one audit row by repository URL."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM repository_audits WHERE repository_url = %s",
            (url,),
        ).fetchone()


def list_audits(limit: int = 20) -> list[dict[str, Any]]:
    """Return recent audits ordered by update time, newest first."""
    with get_db() as conn:
        return conn.execute(
            """
            SELECT id, repository_url, repository_name, commit_sha,
                   scan_status, is_demo, scanner_status, report_json,
                   created_at, updated_at
            FROM repository_audits
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()


def health_check() -> bool:
    """Return True if the database is reachable."""
    try:
        with get_db() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False
