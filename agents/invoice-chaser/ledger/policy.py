"""Whether a reminder may be queued right now. Returns machine-readable reasons."""

from datetime import date

from ledger.ageing import tone_cap
from ledger.config import LedgerConfig


def policy_reasons(*, status: str, due: date, as_of: date, tone_level: int, flags: set[str],
                   pending_reminder: bool, last_sent_on: date | None,
                   config: LedgerConfig) -> list[str]:
    reasons = []
    if status == "PAID":
        reasons.append("INVOICE_PAID")
    if status in ("DISPUTED", "WRITTEN_OFF"):
        reasons.append(f"INVOICE_{status}")
    if (due - as_of).days > config.heads_up_days:
        reasons.append("NOT_DUE_YET")
    if (as_of - due).days > config.max_age_days:
        reasons.append("TOO_OLD_CONSIDER_WRITE_OFF")
    if pending_reminder:
        reasons.append("PENDING_REMINDER_EXISTS")
    if last_sent_on and (as_of - last_sent_on).days < config.cooldown_days:
        reasons.append("COOLDOWN")
    if tone_level > tone_cap(flags):
        reasons.append("TONE_ABOVE_CLIENT_CAP")
    return reasons
