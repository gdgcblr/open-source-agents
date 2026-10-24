import pytest

from ledger import LedgerError
from tests.conftest import payment_id


def outstanding(ledger, inv):
    return ledger.get_invoice(inv)["invoice"]["outstanding"]


def test_tds_payment_auto_applies(agent):
    r = agent.propose_match(payment_id(agent, "ACME"), ["INV-2026-001"], 0.97, "name + TDS")
    assert (r["decision"], r["signal"], r["tds_rate"]) == ("AUTO_APPLIED", "TDS", 0.1)
    assert r["allocations"][0] == {"invoice_id": "INV-2026-001", "paid": "₹45,000", "tds": "₹5,000"}
    assert agent.get_invoice("INV-2026-001")["invoice"]["status"] == "PAID"


def test_same_client_retainer_goes_to_oldest_without_ambiguity(agent):
    r = agent.propose_match(payment_id(agent, "ACME"), ["INV-2026-001"], 0.97, "oldest retainer")
    assert r["ambiguous_with"] == []


def test_same_client_newer_proposal_is_ambiguous(agent):
    r = agent.propose_match(payment_id(agent, "ACME"), ["INV-2026-010"], 0.97, "newer retainer")
    assert r["decision"] == "NEEDS_CONFIRMATION"
    assert r["ambiguous_with"] == ["INV-2026-001"]


def test_exact_foreign_currency(agent):
    r = agent.propose_match(payment_id(agent, "NORTHWIND"), ["INV-2026-003"], 0.95, "name")
    assert (r["decision"], r["signal"]) == ("AUTO_APPLIED", "EXACT")


def test_currency_mismatch_rejected(agent):
    with pytest.raises(LedgerError) as e:
        agent.propose_match(payment_id(agent, "NORTHWIND"), ["INV-2026-007"], 0.95, "x")
    assert e.value.code == "CURRENCY_MISMATCH"


def test_low_name_confidence_needs_confirmation(agent):
    r = agent.propose_match(payment_id(agent, "GREEN LEAF"), ["INV-2026-012"], 0.6, "weak")
    assert r["decision"] == "NEEDS_CONFIRMATION"
    assert outstanding(agent, "INV-2026-012") == "₹28,000"


def test_multi_invoice_always_needs_confirmation_and_flags_other_client(agent):
    r = agent.propose_match(payment_id(agent, "CHAIPOINT"), ["INV-2026-004", "INV-2026-011"], 0.99,
                            "sum of two invoices")
    assert (r["decision"], r["signal"]) == ("NEEDS_CONFIRMATION", "EXACT")
    assert r["ambiguous_with"] == ["INV-2026-002"]  # Bloom's ₹30,000 invoice


def test_partial_needs_confirmation_then_owner_confirms(agent, owner):
    r = agent.propose_match(payment_id(agent, "SHARMA"), ["INV-2026-006"], 0.95, "partial")
    assert (r["decision"], r["signal"]) == ("NEEDS_CONFIRMATION", "PARTIAL")
    assert owner.confirm_match(r["proposal_id"])["status"] == "APPLIED"
    inv = owner.get_invoice("INV-2026-006")["invoice"]
    assert (inv["status"], inv["outstanding"]) == ("PARTIALLY_PAID", "₹12,000")


def test_tds_not_assumed_after_partial_payment(agent, owner):
    pid = payment_id(agent, "SHARMA")
    owner.confirm_match(agent.propose_match(pid, ["INV-2026-006"], 0.95, "p")["proposal_id"])
    # ₹12,000 remains; a ₹10,800 (=90%) payment must be PARTIAL, not TDS
    from ledger.matching import OpenInvoice, amount_signal
    inv = OpenInvoice("INV-2026-006", "C06", "INR", 1_200_000, True, "2026-10-15")
    assert amount_signal(1_080_000, [inv], (0.10,), 100).signal == "PARTIAL"


def test_overpayment_allocates_outstanding_only(agent, owner, tmp_path):
    from tests.conftest import write_csv
    owner.import_payments(write_csv(tmp_path / "b.csv", "date,narration,ref,credit,debit\n"
                                    "2026-10-22,KITE LEARNING,K1,80000,\n"))
    r = agent.propose_match(payment_id(agent, "KITE"), ["INV-2026-005"], 0.99, "overpaid")
    assert (r["decision"], r["signal"], r["unallocated"]) == ("NEEDS_CONFIRMATION", "OVER", "₹5,000")
    owner.confirm_match(r["proposal_id"])
    assert owner.get_invoice("INV-2026-005")["invoice"]["status"] == "PAID"
    assert owner.check_invariants()["ok"]


def test_multi_amount_mismatch_rejected(agent):
    with pytest.raises(LedgerError) as e:
        agent.propose_match(payment_id(agent, "RAHUL"), ["INV-2026-007", "INV-2026-008"], 0.9, "x")
    assert e.value.code == "AMOUNT_MISMATCH"


@pytest.mark.parametrize("kwargs,code", [
    ({"invoice_ids": []}, "INVALID_REQUEST"),
    ({"invoice_ids": "INV-2026-001"}, "INVALID_REQUEST"),
    ({"invoice_ids": ["INV-2026-001", "INV-2026-001"]}, "INVALID_REQUEST"),
    ({"invoice_ids": ["INV-9999"]}, "UNKNOWN_INVOICE"),
    ({"name_confidence": 1.5}, "INVALID_REQUEST"),
    ({"reason": "  "}, "INVALID_REQUEST"),
    ({"invoice_ids": ["INV-2026-007", "INV-2026-012"]}, "INVALID_REQUEST"),  # two clients
])
def test_invalid_proposals(agent, kwargs, code):
    args = {"payment_id": payment_id(agent, "ACME"), "invoice_ids": ["INV-2026-001"],
            "name_confidence": 0.9, "reason": "r", **kwargs}
    with pytest.raises(LedgerError) as e:
        agent.propose_match(**args)
    assert e.value.code == code


def test_unknown_and_already_matched_payment(agent):
    with pytest.raises(LedgerError) as e:
        agent.propose_match(9999, ["INV-2026-001"], 0.9, "r")
    assert e.value.code == "UNKNOWN_PAYMENT"
    pid = payment_id(agent, "ACME")
    agent.propose_match(pid, ["INV-2026-001"], 0.97, "r")
    with pytest.raises(LedgerError) as e:
        agent.propose_match(pid, ["INV-2026-010"], 0.97, "r")
    assert e.value.code == "PAYMENT_ALREADY_MATCHED"


def test_paid_invoice_not_open(agent):
    agent.propose_match(payment_id(agent, "ACME"), ["INV-2026-001"], 0.97, "r")
    with pytest.raises(LedgerError) as e:
        agent.propose_match(payment_id(agent, "RAHUL"), ["INV-2026-001"], 0.9, "r")
    assert e.value.code == "INVOICE_NOT_OPEN"


def test_reject_returns_payment_to_unmatched(agent, owner):
    pid = payment_id(agent, "SHARMA")
    r = agent.propose_match(pid, ["INV-2026-006"], 0.95, "partial")
    assert pid not in [p["payment_id"] for p in agent.list_unmatched_payments()["payments"]]
    owner.reject_match(r["proposal_id"])
    assert pid in [p["payment_id"] for p in agent.list_unmatched_payments()["payments"]]


def test_confirming_one_proposal_supersedes_others(agent, owner):
    pid = payment_id(agent, "CHAIPOINT")
    a = agent.propose_match(pid, ["INV-2026-004", "INV-2026-011"], 0.95, "both chai point")
    b = agent.propose_match(pid, ["INV-2026-002"], 0.2, "same amount, wrong name")
    owner.confirm_match(a["proposal_id"])
    assert owner.list_pending_matches()["proposals"] == []
    assert owner.get_invoice("INV-2026-002")["invoice"]["outstanding"] == "₹30,000"
    with pytest.raises(LedgerError):
        owner.confirm_match(b["proposal_id"])


def test_agent_cannot_confirm(agent):
    r = agent.propose_match(payment_id(agent, "SHARMA"), ["INV-2026-006"], 0.95, "partial")
    with pytest.raises(LedgerError) as e:
        agent.confirm_match(r["proposal_id"])
    assert e.value.code == "FORBIDDEN"
