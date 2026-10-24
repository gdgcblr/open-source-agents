from copy import deepcopy

import pytest

from migine.demo import load_demo
from migine.finance import monthly_summary
from migine.storage import Store


@pytest.fixture
def records(tmp_path):
    store = Store(tmp_path)
    load_demo(store, "2026-10")
    return store.records()


def test_monthly_totals_and_evidence(records):
    report = monthly_summary(records, "2026-10")
    assert report["subscription_totals"]["INR"]["charges"] == "279.00"
    assert report["bills"][0]["status"] == "confirmed_by_email"
    assert len(report["bills"][0]["evidence"]) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("account", "9999"),
        ("provider", "another bank"),
        ("currency", "USD"),
        ("period", "2026-09"),
        ("period", ""),
        ("status", "scheduled"),
        ("status", "received"),
        ("status", "failed"),
        ("status", "reversed"),
        ("occurred_on", "2026-09-01"),
    ],
)
def test_payment_needs_strong_match(records, field, value):
    next(r for r in records if r["data"]["kind"] == "payment")["data"][field] = value
    assert monthly_summary(records, "2026-10")["bills"][0]["credited"] == "0"


def test_partial_and_split_payments(records):
    payment = next(r for r in records if r["data"]["kind"] == "payment")
    payment["data"]["amount"] = "10000.00"
    assert monthly_summary(records, "2026-10")["bills"][0]["status"] == "partial_payment"
    second = deepcopy(payment)
    second["id"] = "second"
    second["data"].update(amount="2450.00", reference="second")
    records.append(second)
    assert monthly_summary(records, "2026-10")["bills"][0]["remaining_from_email"] == "0"


def test_duplicate_confirmation_does_not_double_count(records):
    records.extend(deepcopy(records))
    report = monthly_summary(records, "2026-10")
    assert report["bills"][0]["credited"] == "12450.00"
    assert report["subscription_totals"]["INR"]["charges"] == "279.00"


def test_ambiguous_duplicate_excluded(records):
    charge = next(r for r in records if r["data"]["kind"] == "charge")
    charge["data"]["reference"] = ""
    records.append(deepcopy(charge))
    report = monthly_summary(records, "2026-10")
    assert report["review_needed"]
    assert len(report["subscriptions"]) == 1


def test_conflicting_statement_excluded(records):
    other = deepcopy(next(r for r in records if r["data"]["kind"] == "bill"))
    other["data"]["amount"] = "1.00"
    records.append(other)
    report = monthly_summary(records, "2026-10")
    assert report["bills"] == []
    assert report["review_needed"]


def test_currencies_and_refunds_separate(records):
    charge = deepcopy(next(r for r in records if r["data"]["kind"] == "charge"))
    charge["data"].update(currency="USD", amount="9.99", reference="USD1")
    records.append(charge)
    refund = deepcopy(charge)
    refund["data"].update(kind="refund", amount="2.00", reference="REF1")
    records.append(refund)
    report = monthly_summary(records, "2026-10")
    assert report["subscription_totals"]["USD"] == {
        "charges": "9.99",
        "refunds": "2.00",
        "net": "7.99",
    }
    assert report["subscription_totals"]["INR"]["net"] == "279.00"


def test_month_boundaries(records):
    report = monthly_summary(records, "2026-11")
    assert report["bills"] == []
    assert report["subscription_totals"] == {}


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "garbage"])
def test_invalid_month(records, month):
    with pytest.raises(ValueError):
        monthly_summary(records, month)
