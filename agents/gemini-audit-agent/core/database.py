import sqlite3
from typing import List, Dict, Any
from .models import Member, Expense, SettlementRecord

class AuditDatabase:
    """Local SQLite persistence for Bharat Dues / OmniLedger Audit."""
    
    def __init__(self, db_path="audit_ledger.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS members (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT,
                    amount REAL,
                    payer_id TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(payer_id) REFERENCES members(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settlements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_member TEXT,
                    to_member TEXT,
                    amount REAL,
                    status TEXT DEFAULT 'PENDING',
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(from_member) REFERENCES members(id),
                    FOREIGN KEY(to_member) REFERENCES members(id)
                )
            """)

    def save_member(self, member: Member):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO members (id, name) VALUES (?, ?)", (member.id, member.name))

    def save_expense(self, expense: Expense):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO expenses (description, amount, payer_id) VALUES (?, ?, ?)", 
                         (expense.description, expense.amount, expense.payer_id))

    def get_all_members(self) -> List[Member]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT id, name FROM members")
            return [Member(id=row[0], name=row[1]) for row in cursor.fetchall()]
