"""Deterministic ledger for Invoice Chaser.

Everything that involves money, dates or state lives here. The LLM agents
never touch storage directly; they call these functions (via MCP), and the
functions validate, enforce state machines, and write an audit trail.
"""

from ledger.config import LedgerConfig
from ledger.errors import LedgerError
from ledger.service import Ledger

__all__ = ["Ledger", "LedgerConfig", "LedgerError"]
