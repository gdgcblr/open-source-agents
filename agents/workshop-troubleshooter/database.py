"""
Database & Persistence Layer for Workshop Troubleshooter Agent.
Stores escalated instructor tickets and security audit events using SQLite with
parameterized queries (Zero SQL Injection vulnerabilities).
"""

import sqlite3
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_FILE = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "troubleshooter.db"))


def get_db_connection() -> sqlite3.Connection:
    """Creates a connection with Row factory enabled."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes tables if they do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Tickets Table (Escalated to Instructor)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS escalation_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id TEXT UNIQUE NOT NULL,
        attendee_name TEXT NOT NULL,
        issue_category TEXT NOT NULL,
        error_summary TEXT NOT NULL,
        details TEXT NOT NULL,
        steps_attempted TEXT NOT NULL,
        urgency TEXT DEFAULT 'medium',
        status TEXT DEFAULT 'OPEN',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Security & Interaction Audit Log Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        client_ip TEXT NOT NULL,
        summary TEXT NOT NULL,
        payload_meta TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()


def save_escalation_ticket(
    ticket_id: str,
    attendee_name: str,
    issue_category: str,
    error_summary: str,
    details: str,
    steps_attempted: str,
    urgency: str = "medium",
) -> Dict[str, Any]:
    """Saves an escalated instructor ticket with strict parameterization."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO escalation_tickets 
        (ticket_id, attendee_name, issue_category, error_summary, details, steps_attempted, urgency, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN')
        """,
        (ticket_id, attendee_name, issue_category, error_summary, details, steps_attempted, urgency),
    )
    conn.commit()
    conn.close()

    return {
        "ticket_id": ticket_id,
        "attendee_name": attendee_name,
        "issue_category": issue_category,
        "error_summary": error_summary,
        "urgency": urgency,
        "status": "OPEN",
    }


def fetch_all_tickets() -> List[Dict[str, Any]]:
    """Retrieves all tickets for instructor review."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM escalation_tickets ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_ticket_status(ticket_id: str, new_status: str) -> bool:
    """Updates status (e.g., RESOLVED, IN_PROGRESS)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE escalation_tickets SET status = ? WHERE ticket_id = ?",
        (new_status, ticket_id),
    )
    conn.commit()
    affected = cursor.rowcount > 0
    conn.close()
    return affected


def log_event(event_type: str, client_ip: str, summary: str, meta: Optional[Dict] = None):
    """Safely records an audit trail event."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO audit_logs (event_type, client_ip, summary, payload_meta) VALUES (?, ?, ?, ?)",
        (event_type, client_ip, summary, json.dumps(meta or {})),
    )
    conn.commit()
    conn.close()


def get_troubleshooter_metrics() -> Dict[str, Any]:
    """Returns aggregated stats for instructor dashboard."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM escalation_tickets")
    total_tickets = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM escalation_tickets WHERE status = 'OPEN'")
    open_tickets = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM audit_logs")
    total_interactions = cursor.fetchone()[0]

    cursor.execute("SELECT issue_category, COUNT(*) as count FROM escalation_tickets GROUP BY issue_category")
    categories = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return {
        "total_tickets": total_tickets,
        "open_tickets": open_tickets,
        "resolved_tickets": total_tickets - open_tickets,
        "total_interactions": total_interactions,
        "categories_breakdown": categories,
    }


# Auto-initialize database on import
init_db()
