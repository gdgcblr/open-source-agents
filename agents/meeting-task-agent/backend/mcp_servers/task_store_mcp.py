import sqlite3
import json
from typing import Dict, Any, List, Optional
from config import settings

class TaskStoreMCPServer:
    """
    SQLite-backed Task Store MCP Server for task lifecycle,
    persistent reminders, and state synchronization.
    """
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.db_path
        self._init_db()
        
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    meeting_id TEXT,
                    meeting_title TEXT,
                    owner TEXT,
                    owner_email TEXT,
                    task TEXT,
                    deadline TEXT,
                    priority TEXT DEFAULT 'medium',
                    status TEXT DEFAULT 'pending',
                    calendar_event_id TEXT,
                    calendar_event_url TEXT,
                    last_nudged_at TEXT,
                    nudge_count INTEGER DEFAULT 0,
                    created_at TEXT,
                    completed_at TEXT
                )
            """)
            conn.commit()

    def upsert_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO tasks (
                    id, meeting_id, meeting_title, owner, owner_email,
                    task, deadline, priority, status, calendar_event_id,
                    calendar_event_url, last_nudged_at, nudge_count,
                    created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    deadline = excluded.deadline,
                    status = excluded.status,
                    calendar_event_id = COALESCE(excluded.calendar_event_id, tasks.calendar_event_id),
                    calendar_event_url = COALESCE(excluded.calendar_event_url, tasks.calendar_event_url),
                    last_nudged_at = excluded.last_nudged_at,
                    nudge_count = excluded.nudge_count,
                    completed_at = excluded.completed_at
            """, (
                task["id"],
                task.get("meetingId") or task.get("meeting_id", ""),
                task.get("meetingTitle") or task.get("meeting_title", ""),
                task.get("owner", ""),
                task.get("ownerEmail") or task.get("owner_email"),
                task.get("task", ""),
                task.get("deadline"),
                task.get("priority", "medium"),
                task.get("status", "pending"),
                task.get("calendarEventId") or task.get("calendar_event_id"),
                task.get("calendarEventUrl") or task.get("calendar_event_url"),
                task.get("lastNudgedAt") or task.get("last_nudged_at"),
                task.get("nudgeCount") or task.get("nudge_count", 0),
                task.get("createdAt") or task.get("created_at", "now"),
                task.get("completedAt") or task.get("completed_at")
            ))
            conn.commit()
        return task

    def get_all_tasks(self, owner: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if owner and owner != "all":
            query += " AND owner = ?"
            params.append(owner)
        if status and status != "all":
            query += " AND status = ?"
            params.append(status)
            
        query += " ORDER BY created_at DESC"
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def update_task_status(self, task_id: str, new_status: str, completed_at: Optional[str] = None) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("""
                UPDATE tasks
                SET status = ?, completed_at = ?
                WHERE id = ?
            """, (new_status, completed_at, task_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_pending_nudge_candidates(self) -> List[Dict[str, Any]]:
        """
        Retrieves tasks where status is pending and deadline is missing or overdue.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM tasks
                WHERE status = 'pending' AND (deadline IS NULL OR deadline < datetime('now'))
            """)
            return [dict(row) for row in cursor.fetchall()]

