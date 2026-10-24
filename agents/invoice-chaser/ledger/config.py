import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent


def db_path() -> Path:
    """INVOICE_CHASER_DB, with relative paths resolved against the project folder so the
    CLI, the MCP server and `adk web` always open the same file."""
    path = Path(os.getenv("INVOICE_CHASER_DB") or "data/ledger.db")
    return path if path.is_absolute() else PROJECT_DIR / path


@dataclass(frozen=True)
class LedgerConfig:
    # Payment matching
    tds_rates: tuple[float, ...] = (0.10,)
    tolerance_paise: int = 100  # ₹1 rounding tolerance
    auto_apply_min_name_confidence: float = 0.90

    # Reminder policy
    heads_up_days: int = 3  # tone-0 reminder allowed this many days before due
    cooldown_days: int = 5
    max_age_days: int = 180  # older invoices are surfaced, not auto-chased

    # Rendering
    sender_name: str = "Priya"
    payment_details: str = "the bank details on the invoice"
    max_subject_chars: int = 120
    max_body_chars: int = 1200

    # Date parsing for ambiguous formats like 03/04/2026
    day_first: bool = True

    # Fixed "today" for reproducible demos and tests (None = real date)
    today_override: date | None = field(default=None)

    def today(self) -> date:
        return self.today_override or date.today()

    @classmethod
    def from_env(cls) -> "LedgerConfig":
        kwargs = {}
        if v := os.getenv("INVOICE_CHASER_TODAY"):
            kwargs["today_override"] = date.fromisoformat(v)
        if v := os.getenv("INVOICE_CHASER_TDS_RATES"):
            kwargs["tds_rates"] = tuple(float(x) for x in v.split(","))
        if v := os.getenv("INVOICE_CHASER_SENDER_NAME"):
            kwargs["sender_name"] = v
        if v := os.getenv("INVOICE_CHASER_PAYMENT_DETAILS"):
            kwargs["payment_details"] = v
        return cls(**kwargs)
