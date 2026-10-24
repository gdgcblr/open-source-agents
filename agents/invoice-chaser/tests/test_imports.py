import pytest

from ledger import Ledger, LedgerError
from tests.conftest import SAMPLE, write_csv


def test_sample_import_counts(owner):
    assert len(owner.list_open_invoices()["invoices"]) == 12
    assert len(owner.list_unmatched_payments()["payments"]) == 7  # debit row ignored


def test_reimport_is_idempotent(owner):
    assert owner.import_clients(str(SAMPLE / "clients.csv")) == {"ok": True, "imported": 0, "unchanged": 8}
    inv = owner.import_invoices(str(SAMPLE / "invoices.csv"))
    assert (inv["imported"], inv["unchanged"]) == (0, 12)
    pay = owner.import_payments(str(SAMPLE / "bank_statement.csv"))
    assert (pay["imported"], pay["duplicates_skipped"]) == (0, 7)


def test_missing_columns_rejected(db_path, config, tmp_path):
    led = Ledger(db_path, config)
    path = write_csv(tmp_path / "c.csv", "client_id,name\nC1,Foo\n")
    with pytest.raises(LedgerError) as e:
        led.import_clients(path)
    assert e.value.code == "IMPORT_INVALID"
    assert "missing column: email" in e.value.details["errors"]


def test_bad_invoice_rows_import_nothing(owner, tmp_path):
    path = write_csv(tmp_path / "i.csv",
                     "invoice_no,client_id,issue_date,due_date,amount\n"
                     "NEW-1,C01,2026-10-01,2026-10-31,1000\n"      # valid
                     "NEW-2,C99,2026-10-01,2026-10-31,1000\n"      # unknown client
                     "NEW-3,C01,2026-10-31,2026-10-01,1000\n"      # due before issue
                     "NEW-4,C01,2026-10-01,2026-10-31,-5\n"        # negative
                     "NEW-1,C01,2026-10-01,2026-10-31,1000\n")     # duplicate in file
    with pytest.raises(LedgerError) as e:
        owner.import_invoices(path)
    assert len(e.value.details["errors"]) == 4
    assert len(owner.list_open_invoices()["invoices"]) == 12  # nothing imported


def test_conflicting_existing_invoice_rejected(owner, tmp_path):
    path = write_csv(tmp_path / "i.csv",
                     "invoice_no,client_id,issue_date,due_date,amount\n"
                     "INV-2026-001,C01,2026-08-01,2026-08-31,99999\n")
    with pytest.raises(LedgerError) as e:
        owner.import_invoices(path)
    assert "amount_paise" in e.value.details["errors"][0]


def test_ambiguous_dates_warned(owner, tmp_path):
    path = write_csv(tmp_path / "i.csv",
                     "invoice_no,client_id,issue_date,due_date,amount\n"
                     "NEW-9,C01,03/04/2026,2026-05-30,1000\n")
    result = owner.import_invoices(path)
    assert result["imported"] == 1
    assert "ambiguous date" in result["warnings"][0]


def test_latin1_csv_is_readable(owner, tmp_path):
    path = tmp_path / "c.csv"
    path.write_bytes("client_id,name,contact_name,email,language\nC50,Café Noir,José,j@x.example,en\n"
                     .encode("latin-1"))
    assert owner.import_clients(str(path))["imported"] == 1


def test_bank_rows_validated(owner, tmp_path):
    path = write_csv(tmp_path / "b.csv", "date,narration,ref,credit,debit\n"
                                         "not-a-date,X,,100,\n2026-10-01,Y,,,\n")
    with pytest.raises(LedgerError) as e:
        owner.import_payments(path)
    assert len(e.value.details["errors"]) == 2


def test_agent_cannot_import(agent):
    with pytest.raises(LedgerError) as e:
        agent.import_payments(str(SAMPLE / "bank_statement.csv"))
    assert e.value.code == "FORBIDDEN"
