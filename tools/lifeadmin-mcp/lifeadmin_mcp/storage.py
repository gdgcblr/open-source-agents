"""SQLite persistence and validation for LifeAdmin reminders."""

from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Iterator, Literal

ReminderStatus = Literal["upcoming", "overdue", "completed", "all"]
DEFAULT_DB_PATH = Path.home() / ".lifeadmin" / "reminders.sqlite3"


def _database_path() -> Path:
    return Path(os.environ.get("LIFEADMIN_DB_PATH", DEFAULT_DB_PATH)).expanduser()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
                due_date TEXT NOT NULL,
                due_time TEXT,
                category TEXT,
                notes TEXT,
                status TEXT NOT NULL DEFAULT 'open'
                    CHECK(status IN ('open', 'completed')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _validate_title(title: str) -> str:
    cleaned = title.strip()
    if not cleaned or len(cleaned) > 200:
        raise ValueError("title must contain between 1 and 200 characters")
    return cleaned


def _validate_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError("due_date must be a calendar date in YYYY-MM-DD format") from error
    if parsed.isoformat() != value:
        raise ValueError("due_date must be a calendar date in YYYY-MM-DD format")
    return value


def _validate_time(value: str | None) -> str | None:
    if value is None:
        return None
    if (
        len(value) != 5
        or value[2] != ":"
        or not value[:2].isdigit()
        or not value[3:].isdigit()
    ):
        raise ValueError("due_time must use 24-hour HH:MM format")
    try:
        parsed = time.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError("due_time must use 24-hour HH:MM format") from error
    return parsed.strftime("%H:%M")


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def add_reminder(
    title: str,
    due_date: str,
    due_time: str | None = None,
    category: str | None = None,
    notes: str | None = None,
) -> dict[str, str | None]:
    """Create a reminder and return its persisted fields."""
    title = _validate_title(title)
    due_date = _validate_date(due_date)
    due_time = _validate_time(due_time)
    if category is not None and len(category.strip()) > 80:
        raise ValueError("category must be 80 characters or fewer")
    if notes is not None and len(notes) > 2000:
        raise ValueError("notes must be 2000 characters or fewer")

    reminder_id = str(uuid.uuid4())
    timestamp = _timestamp()
    values: dict[str, str | None] = {
        "id": reminder_id,
        "title": title,
        "due_date": due_date,
        "due_time": due_time,
        "category": category.strip() if category else None,
        "notes": notes,
        "status": "open",
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO reminders
                (id, title, due_date, due_time, category, notes, status, created_at, updated_at)
            VALUES
                (:id, :title, :due_date, :due_time, :category, :notes, :status, :created_at, :updated_at)
            """,
            values,
        )
    return values


def list_reminders(
    status: ReminderStatus = "upcoming",
    limit: int = 50,
    as_of_date: str | None = None,
) -> list[dict[str, str | None]]:
    """List reminders, using local calendar date for upcoming/overdue filtering."""
    if status not in ("upcoming", "overdue", "completed", "all"):
        raise ValueError("status must be upcoming, overdue, completed, or all")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    today = _validate_date(as_of_date) if as_of_date else date.today().isoformat()
    conditions = {
        "upcoming": ("status = 'open' AND due_date >= ?", (today,)),
        "overdue": ("status = 'open' AND due_date < ?", (today,)),
        "completed": ("status = 'completed'", ()),
        "all": ("1 = 1", ()),
    }
    where_clause, parameters = conditions[status]
    with _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT id, title, due_date, due_time, category, notes, status, created_at, updated_at
            FROM reminders
            WHERE {where_clause}
            ORDER BY due_date, due_time IS NULL, due_time, created_at, id
            LIMIT ?
            """,
            (*parameters, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def find_reminders(query: str, limit: int = 20) -> list[dict[str, str | None]]:
    """Find reminders whose title contains the case-insensitive query."""
    cleaned_query = query.strip()
    if not cleaned_query or len(cleaned_query) > 200:
        raise ValueError("query must contain between 1 and 200 characters")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, title, due_date, due_time, category, notes, status, created_at, updated_at
            FROM reminders
            WHERE instr(lower(title), lower(?)) > 0
            ORDER BY due_date, due_time IS NULL, due_time, created_at, id
            LIMIT ?
            """,
            (cleaned_query, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def _resolve_reminder_id(
    connection: sqlite3.Connection,
    reminder_id: str | None,
    match_title: str | None,
) -> str:
    if reminder_id and match_title:
        raise ValueError("provide reminder_id or match_title, not both")
    if reminder_id:
        return reminder_id
    if match_title is None or not match_title.strip():
        raise ValueError("provide a reminder_id or a non-empty match_title")
    matches = connection.execute(
        """
        SELECT id FROM reminders
        WHERE instr(lower(title), lower(?)) > 0
        ORDER BY due_date, due_time IS NULL, due_time, created_at, id
        LIMIT 2
        """,
        (match_title.strip(),),
    ).fetchall()
    if not matches:
        raise ValueError(f"no reminder matches title: {match_title.strip()}")
    if len(matches) > 1:
        raise ValueError(
            f"multiple reminders match title: {match_title.strip()}; "
            "use find_reminders to identify the intended reminder"
        )
    return str(matches[0]["id"])


def update_reminder(
    reminder_id: str | None = None,
    title: str | None = None,
    due_date: str | None = None,
    due_time: str | None = None,
    category: str | None = None,
    notes: str | None = None,
    clear_due_time: bool = False,
    match_title: str | None = None,
) -> dict[str, str | None]:
    """Update supplied reminder fields; omitted values are left unchanged."""
    if not reminder_id and not match_title:
        raise ValueError("provide a reminder_id or match_title")
    if clear_due_time and due_time is not None:
        raise ValueError("provide due_time or clear_due_time, not both")
    changes: dict[str, str | None] = {}
    if title is not None:
        changes["title"] = _validate_title(title)
    if due_date is not None:
        changes["due_date"] = _validate_date(due_date)
    if due_time is not None:
        changes["due_time"] = _validate_time(due_time)
    elif clear_due_time:
        changes["due_time"] = None
    if category is not None:
        if len(category.strip()) > 80:
            raise ValueError("category must be 80 characters or fewer")
        changes["category"] = category.strip() or None
    if notes is not None:
        if len(notes) > 2000:
            raise ValueError("notes must be 2000 characters or fewer")
        changes["notes"] = notes
    if not changes:
        raise ValueError("provide at least one field to update")

    changes["updated_at"] = _timestamp()
    with _connect() as connection:
        resolved_id = _resolve_reminder_id(connection, reminder_id, match_title)
        cursor = connection.execute(
            "UPDATE reminders SET "
            + ", ".join(f"{field} = :{field}" for field in changes)
            + " WHERE id = :reminder_id",
            {**changes, "reminder_id": resolved_id},
        )
        if cursor.rowcount == 0:
            raise ValueError(f"reminder not found: {resolved_id}")
        row = connection.execute(
            """
            SELECT id, title, due_date, due_time, category, notes, status, created_at, updated_at
            FROM reminders WHERE id = ?
            """,
            (resolved_id,),
        ).fetchone()
    return dict(row)


def mark_completed(
    reminder_id: str | None = None,
    match_title: str | None = None,
) -> dict[str, str | None]:
    """Mark one reminder completed by ID or an unambiguous title match."""
    with _connect() as connection:
        resolved_id = _resolve_reminder_id(connection, reminder_id, match_title)
        cursor = connection.execute(
            "UPDATE reminders SET status = 'completed', updated_at = ? WHERE id = ?",
            (_timestamp(), resolved_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"reminder not found: {resolved_id}")
        row = connection.execute(
            """
            SELECT id, title, due_date, due_time, category, notes, status, created_at, updated_at
            FROM reminders WHERE id = ?
            """,
            (resolved_id,),
        ).fetchone()
    return dict(row)


def get_current_date() -> dict[str, str]:
    """Return the local date and timezone to ground relative-date interpretation."""
    now = datetime.now().astimezone()
    timezone = now.tzname() or "local time"
    return {"current_date": now.date().isoformat(), "timezone": timezone}
