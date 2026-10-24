"""Ageing, priority and recommended tone. Pure functions over plain values."""

from datetime import date

FLAG_GENTLE = "gentle"
FLAG_ALLOW_FINAL = "allow_final_notice"


def days_overdue(due: date, as_of: date) -> int:
    return (as_of - due).days  # negative = not yet due


def bucket(overdue_days: int) -> str:
    if overdue_days <= 0:
        return "not_overdue"
    if overdue_days <= 15:
        return "1-15"
    if overdue_days <= 30:
        return "16-30"
    if overdue_days <= 60:
        return "31-60"
    return "60+"


def tone_for_age(overdue_days: int) -> int:
    if overdue_days <= 0:
        return 0
    if overdue_days <= 7:
        return 1
    if overdue_days <= 30:
        return 2
    return 3


def tone_cap(flags: set[str]) -> int:
    if FLAG_GENTLE in flags:
        return 1
    if FLAG_ALLOW_FINAL in flags:
        return 3
    return 2  # final notice requires per-client opt-in


def recommended_tone(overdue_days: int, flags: set[str], last_sent_tone: int | None) -> int:
    level = tone_for_age(overdue_days)
    if last_sent_tone is not None and overdue_days > 0:
        level = max(level, last_sent_tone)  # never de-escalate an overdue chase
    return min(level, tone_cap(flags))


def priority(outstanding_paise: int, overdue_days: int) -> float:
    """Bigger and older first. Not-yet-due items are negative (sooner due = higher),
    so they always rank below every overdue one."""
    if overdue_days <= 0:
        return float(overdue_days - 1)
    return round(outstanding_paise / 100_000 * (1 + overdue_days / 7), 2)
