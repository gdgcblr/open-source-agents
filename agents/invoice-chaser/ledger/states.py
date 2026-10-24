"""State machines. Invoice status is mostly *computed*; only holds are stored."""

from datetime import date

from ledger.errors import LedgerError

# --- Invoice --------------------------------------------------------------

OPEN_STATUSES = {"SENT", "DUE", "OVERDUE", "PARTIALLY_PAID"}

# Holds the owner can place or clear. (None = no hold.)
HOLD_TRANSITIONS = {
    None: {"DISPUTED", "WRITTEN_OFF"},
    "DISPUTED": {None, "WRITTEN_OFF"},
    "WRITTEN_OFF": set(),  # terminal
}


def invoice_status(*, amount: int, settled: int, hold: str | None, due: date,
                   as_of: date, heads_up_days: int, tolerance: int) -> str:
    if hold:
        return hold
    if settled >= amount - tolerance:
        return "PAID"
    if settled > 0:
        return "PARTIALLY_PAID"
    if as_of > due:
        return "OVERDUE"
    if (due - as_of).days <= heads_up_days:
        return "DUE"
    return "SENT"


def check_hold_transition(current: str | None, new: str | None, status: str) -> None:
    if status == "PAID" and new is not None:
        raise LedgerError("ILLEGAL_TRANSITION", "A paid invoice cannot be disputed or written off")
    if new not in HOLD_TRANSITIONS[current]:
        raise LedgerError("ILLEGAL_TRANSITION", f"Cannot change hold from {current} to {new}")


# --- Reminder -------------------------------------------------------------

REMINDER_TRANSITIONS = {
    "QUEUED": {"APPROVED", "SKIPPED", "CANCELLED"},
    "APPROVED": {"SENT", "CANCELLED"},
    "SENT": {"RESPONDED"},
    "DROPPED": set(),
    "SKIPPED": set(),
    "CANCELLED": set(),
    "RESPONDED": set(),
}
PENDING_REMINDER_STATUSES = {"QUEUED", "APPROVED"}


def check_reminder_transition(current: str, new: str) -> None:
    if new not in REMINDER_TRANSITIONS.get(current, set()):
        raise LedgerError("ILLEGAL_TRANSITION", f"Cannot move reminder from {current} to {new}")
