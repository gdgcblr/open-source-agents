"""Comprehensive Test Suite for Gemini Audit Agent & Invariants."""
from __future__ import annotations
import pytest
from core.models import Member, Expense, SettlementRecord, SettlementStatus
from core.member_resolver import clean_phone_digits, resolve_canonical_member_id, build_canonical_member_index
from core.ledger import compute_member_balances, settle_balances, audit_ledger
from core.gemini_parser import parse_unstructured_ledger


def test_canonical_id_resolution_phone_variants():
    members = [
        Member(id="m_alice", name="Alice", uid="firebase_uid_alice", phone_number="+919876543210"),
        Member(id="m_bob", name="Bob", uid="firebase_uid_bob", phone_number="9999988888"),
    ]
    index = build_canonical_member_index(members)

    # Resolves direct ID
    assert resolve_canonical_member_id("m_alice", members, index) == "m_alice"
    # Resolves Firebase UID
    assert resolve_canonical_member_id("firebase_uid_alice", members, index) == "m_alice"
    # Resolves 10-digit phone number
    assert resolve_canonical_member_id("+919876543210", members, index) == "m_alice"
    assert resolve_canonical_member_id("9876543210", members, index) == "m_alice"
    assert resolve_canonical_member_id("09876543210", members, index) == "m_alice"
    # Resolves Bob
    assert resolve_canonical_member_id("firebase_uid_bob", members, index) == "m_bob"
    assert resolve_canonical_member_id("+919999988888", members, index) == "m_bob"


def test_devfest_discrepancy_reproduction_scenario():
    """Exact DevFest issue:
    1. Transaction 1: 3000 paid by Alice, split 2 ways with Bob.
    2. Bob pays Alice 1400 (Pending confirmation from Alice).
    Audit must show:
    - Alice balance: +1500 (gets back)
    - Bob balance: -1500 (owes)
    - Net sum == 0.00
    - Pending settlement is quarantined in anomalies and does not corrupt confirmed balances.
    """
    members = [
        Member(id="alice", name="Alice", uid="uid_a"),
        Member(id="bob", name="Bob", phone_number="+919999988888"),
    ]

    expense = Expense(
        description="Dinner",
        payer_id="uid_a",  # Using UID
        amount=3000.0,
        shares={"alice": 1500.0, "bob": 1500.0},
    )

    pending_payment = SettlementRecord(
        from_member_id="bob",
        from_name="Bob",
        to_member_id="alice",
        to_name="Alice",
        amount=1400.0,
        status=SettlementStatus.pending,
    )

    report = audit_ledger(members, [expense], [pending_payment])

    # 1. Invariant check
    assert report.is_balanced is True
    assert abs(report.net_zero_delta) < 0.0001

    # 2. Balance check
    assert report.member_balances["alice"] == 1500.0
    assert report.member_balances["bob"] == -1500.0

    # 3. Pending payment check
    assert report.pending_settlements_count == 1
    pending_anomalies = [a for a in report.anomalies if a.type == "PENDING_HOLD"]
    assert len(pending_anomalies) == 1

    # 4. Optimal settlement check
    assert len(report.optimal_settlements) == 1
    assert report.optimal_settlements[0].from_name == "Bob"
    assert report.optimal_settlements[0].to_name == "Alice"
    assert report.optimal_settlements[0].amount == 1500.0


def test_settlement_confirmation_lifecycle():
    members = [
        Member(id="alice", name="Alice"),
        Member(id="bob", name="Bob"),
    ]

    expense = Expense(
        description="Hotel",
        payer_id="alice",
        amount=2000.0,
        shares={"alice": 1000.0, "bob": 1000.0},
    )

    # Bob confirms payment of 1000
    confirmed_payment = SettlementRecord(
        from_member_id="bob",
        from_name="Bob",
        to_member_id="alice",
        to_name="Alice",
        amount=1000.0,
        status=SettlementStatus.confirmed,
    )

    report = audit_ledger(members, [expense], [confirmed_payment])
    assert report.is_balanced is True
    assert report.member_balances["alice"] == 0.0
    assert report.member_balances["bob"] == 0.0
    assert len(report.optimal_settlements) == 0


def test_heuristic_offline_parser():
    sample_text = """Dinner of 3000 paid by Alice split with Bob.
Bob paid Alice 1400 pending."""
    members, expenses, settlements = parse_unstructured_ledger(sample_text)

    assert len(expenses) >= 1
    assert expenses[0].amount == 3000.0
    assert expenses[0].payer_id == "alice"

    assert len(settlements) >= 1
    assert settlements[0].amount == 1400.0
    assert settlements[0].status == SettlementStatus.pending


def test_split_mismatch_anomaly_detection():
    members = [
        Member(id="alice", name="Alice"),
        Member(id="bob", name="Bob"),
    ]
    # Broken split: 3000 total but shares only sum to 2000
    broken_expense = Expense(
        description="Erroneous Split",
        payer_id="alice",
        amount=3000.0,
        shares={"alice": 1000.0, "bob": 1000.0},
    )
    report = audit_ledger(members, [broken_expense], [])
    mismatches = [a for a in report.anomalies if a.type == "SPLIT_MISMATCH"]
    assert len(mismatches) == 1
    assert mismatches[0].severity == "HIGH"
