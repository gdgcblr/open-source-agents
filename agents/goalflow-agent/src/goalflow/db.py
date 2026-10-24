"""Database layer for GoalFlow using SQLite."""

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from typing import Generator, List, Optional

from goalflow.config import get_db_path
from goalflow.models import (
    Achievement,
    CheckIn,
    Goal,
    GoalLevel,
    GoalStatus,
    Reflection,
)

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    level TEXT NOT NULL,
    category TEXT NOT NULL,
    parent_id INTEGER NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    target_date TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (parent_id) REFERENCES goals (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_text TEXT NOT NULL,
    summary TEXT NOT NULL,
    completed_notes TEXT NOT NULL DEFAULT '',
    blockers TEXT NOT NULL DEFAULT '',
    next_day_priority TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    goal_id INTEGER NULL,
    milestone_date TEXT NOT NULL,
    notes TEXT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (goal_id) REFERENCES goals (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS check_ins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_in_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    created_at TEXT NOT NULL
);
"""


@contextmanager
def get_connection(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    """Provide a transactional SQLite database connection."""
    path = db_path if db_path is not None else get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize database schema if it doesn't already exist."""
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)


def _row_to_goal(row: sqlite3.Row) -> Goal:
    return Goal(
        id=row["id"],
        title=row["title"],
        level=GoalLevel(row["level"]),
        category=row["category"],
        parent_id=row["parent_id"],
        status=GoalStatus(row["status"]),
        target_date=row["target_date"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def create_goal(
    title: str,
    level: str | GoalLevel,
    category: str,
    parent_id: Optional[int] = None,
    target_date: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Goal:
    """Create a new goal and persist it in the database."""
    if not title or not title.strip():
        raise ValueError("Goal title cannot be empty.")

    goal_level = level if isinstance(level, GoalLevel) else GoalLevel.from_str(level)
    cat = category.strip().lower() if category else "general"

    now_iso = datetime.now().isoformat()

    with get_connection(db_path) as conn:
        if parent_id is not None:
            parent = conn.execute("SELECT id, level FROM goals WHERE id = ?", (parent_id,)).fetchone()
            if not parent:
                raise ValueError(f"Parent goal with ID {parent_id} does not exist.")

        cursor = conn.execute(
            """
            INSERT INTO goals (title, level, category, parent_id, status, target_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title.strip(),
                goal_level.value,
                cat,
                parent_id,
                GoalStatus.PENDING.value,
                target_date,
                now_iso,
                now_iso,
            ),
        )
        goal_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        return _row_to_goal(row)


def get_goal(goal_id: int, db_path: Optional[str] = None) -> Optional[Goal]:
    """Retrieve a single goal by its ID."""
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        return _row_to_goal(row) if row else None


def list_goals(
    level: Optional[str | GoalLevel] = None,
    status: Optional[str | GoalStatus] = None,
    parent_id: Optional[int] = None,
    db_path: Optional[str] = None,
) -> List[Goal]:
    """List goals filtered by level, status, or parent_id."""
    query = "SELECT * FROM goals WHERE 1=1"
    params = []

    if level is not None:
        goal_level = level if isinstance(level, GoalLevel) else GoalLevel.from_str(level)
        query += " AND level = ?"
        params.append(goal_level.value)

    if status is not None:
        goal_status = status if isinstance(status, GoalStatus) else GoalStatus.from_str(status)
        query += " AND status = ?"
        params.append(goal_status.value)

    if parent_id is not None:
        query += " AND parent_id = ?"
        params.append(parent_id)

    query += " ORDER BY id ASC"

    with get_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
        return [_row_to_goal(r) for r in rows]


def update_goal_status(
    goal_id: int,
    status: str | GoalStatus,
    db_path: Optional[str] = None,
) -> Goal:
    """Update status of a goal (pending, in_progress, completed, abandoned)."""
    goal_status = status if isinstance(status, GoalStatus) else GoalStatus.from_str(status)
    now_iso = datetime.now().isoformat()

    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "UPDATE goals SET status = ?, updated_at = ? WHERE id = ?",
            (goal_status.value, now_iso, goal_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Goal with ID {goal_id} not found.")

        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        return _row_to_goal(row)


def delete_goal(goal_id: int, db_path: Optional[str] = None) -> bool:
    """Delete a goal by ID."""
    with get_connection(db_path) as conn:
        cursor = conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
        return cursor.rowcount > 0


def create_reflection(
    raw_text: str,
    summary: str,
    completed_notes: str = "",
    blockers: str = "",
    next_day_priority: str = "",
    db_path: Optional[str] = None,
) -> Reflection:
    """Store a daily reflection entry."""
    if not raw_text or not raw_text.strip():
        raise ValueError("Reflection text cannot be empty.")

    now_iso = datetime.now().isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO reflections (raw_text, summary, completed_notes, blockers, next_day_priority, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                raw_text.strip(),
                summary.strip(),
                completed_notes.strip(),
                blockers.strip(),
                next_day_priority.strip(),
                now_iso,
            ),
        )
        ref_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM reflections WHERE id = ?", (ref_id,)).fetchone()
        return Reflection(
            id=row["id"],
            raw_text=row["raw_text"],
            summary=row["summary"],
            completed_notes=row["completed_notes"],
            blockers=row["blockers"],
            next_day_priority=row["next_day_priority"],
            created_at=row["created_at"],
        )


def list_reflections(limit: int = 10, db_path: Optional[str] = None) -> List[Reflection]:
    """Retrieve recent reflections."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM reflections ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            Reflection(
                id=r["id"],
                raw_text=r["raw_text"],
                summary=r["summary"],
                completed_notes=r["completed_notes"],
                blockers=r["blockers"],
                next_day_priority=r["next_day_priority"],
                created_at=r["created_at"],
            )
            for r in rows
        ]


def create_achievement(
    title: str,
    category: str = "general",
    goal_id: Optional[int] = None,
    milestone_date: Optional[str] = None,
    notes: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Achievement:
    """Store a verified milestone or achievement."""
    if not title or not title.strip():
        raise ValueError("Achievement title cannot be empty.")

    m_date = milestone_date or date.today().isoformat()
    now_iso = datetime.now().isoformat()
    cat = category.strip().lower() if category else "general"

    with get_connection(db_path) as conn:
        if goal_id is not None:
            goal = conn.execute("SELECT id FROM goals WHERE id = ?", (goal_id,)).fetchone()
            if not goal:
                raise ValueError(f"Associated goal ID {goal_id} does not exist.")

        cursor = conn.execute(
            """
            INSERT INTO achievements (title, category, goal_id, milestone_date, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (title.strip(), cat, goal_id, m_date, notes, now_iso),
        )
        ach_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM achievements WHERE id = ?", (ach_id,)).fetchone()
        return Achievement(
            id=row["id"],
            title=row["title"],
            category=row["category"],
            goal_id=row["goal_id"],
            milestone_date=row["milestone_date"],
            notes=row["notes"],
            created_at=row["created_at"],
        )


def list_achievements(
    category: Optional[str] = None,
    limit: Optional[int] = None,
    db_path: Optional[str] = None,
) -> List[Achievement]:
    """List achievements, optionally filtered by category and limited in count."""
    query = "SELECT * FROM achievements WHERE 1=1"
    params = []

    if category:
        query += " AND category = ?"
        params.append(category.strip().lower())

    query += " ORDER BY milestone_date DESC, id DESC"

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    with get_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
        return [
            Achievement(
                id=r["id"],
                title=r["title"],
                category=r["category"],
                goal_id=r["goal_id"],
                milestone_date=r["milestone_date"],
                notes=r["notes"],
                created_at=r["created_at"],
            )
            for r in rows
        ]


def record_check_in(
    check_in_date: Optional[str] = None,
    status: str = "completed",
    db_path: Optional[str] = None,
) -> CheckIn:
    """Record a daily check-in."""
    c_date = check_in_date or date.today().isoformat()
    now_iso = datetime.now().isoformat()

    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO check_ins (check_in_date, status, created_at) VALUES (?, ?, ?)",
            (c_date, status, now_iso),
        )
        cid = cursor.lastrowid
        row = conn.execute("SELECT * FROM check_ins WHERE id = ?", (cid,)).fetchone()
        return CheckIn(
            id=row["id"],
            check_in_date=row["check_in_date"],
            status=row["status"],
            created_at=row["created_at"],
        )


def get_latest_check_in(db_path: Optional[str] = None) -> Optional[CheckIn]:
    """Return the most recent check-in."""
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM check_ins ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return None
        return CheckIn(
            id=row["id"],
            check_in_date=row["check_in_date"],
            status=row["status"],
            created_at=row["created_at"],
        )
