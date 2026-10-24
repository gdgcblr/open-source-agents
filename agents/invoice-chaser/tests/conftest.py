from datetime import date
from pathlib import Path

import pytest

from ledger import Ledger, LedgerConfig

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data"
TODAY = date(2026, 10, 24)

GOOD_SUBJECT = "Invoice {invoice_no}"
GOOD_BODY = ("Hi {client_first_name}, a gentle reminder that invoice {invoice_no} for "
             "{amount_due} was due on {due_date}. Thanks, {sender_name}")


@pytest.fixture
def config():
    return LedgerConfig(today_override=TODAY)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "ledger.db"


@pytest.fixture
def owner(db_path, config):
    """Owner ledger loaded with the bundled sample data."""
    led = Ledger(db_path, config, actor="owner")
    led.import_clients(str(SAMPLE / "clients.csv"))
    led.import_invoices(str(SAMPLE / "invoices.csv"))
    led.import_payments(str(SAMPLE / "bank_statement.csv"))
    yield led
    led.close()


@pytest.fixture
def agent(owner, db_path, config):
    """Agent-scoped ledger on the same database."""
    led = Ledger(db_path, config, actor="agent")
    yield led
    led.close()


def payment_id(ledger, narration_fragment: str) -> int:
    for p in ledger.list_unmatched_payments()["payments"]:
        if narration_fragment in p["narration_untrusted"]:
            return p["payment_id"]
    raise LookupError(narration_fragment)


def write_csv(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return str(path)
