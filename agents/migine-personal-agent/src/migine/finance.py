from collections import defaultdict
from datetime import date
from decimal import Decimal


def month_key(value: str) -> str:
    date.fromisoformat(value + "-01")
    return value


def unique_transactions(records):
    """A reference is required for reliable deduplication; ambiguous groups are excluded."""
    groups = defaultdict(list)
    for row in records:
        d = row["data"]
        identity = (d["kind"], d["provider"], d["account"], d["currency"])
        key = identity + (
            ("ref", d["reference"])
            if d["reference"]
            else ("possible", d["occurred_on"], d["amount"])
        )
        groups[key].append(row)
    result, issues = [], []
    for rows in groups.values():
        values = {r["data"]["amount"] for r in rows}
        statuses = {r["data"]["status"] for r in rows}
        if len(values) > 1 or (len(rows) > 1 and not rows[0]["data"]["reference"]):
            issues.append(
                {
                    "reason": "Possible duplicate or conflicting amount; excluded",
                    "record_ids": [r["id"] for r in rows],
                }
            )
            continue
        if statuses & {"reversed", "failed"}:
            continue
        result.append(
            max(rows, key=lambda r: (r["data"]["status"] == "credited", r["data"]["occurred_on"]))
        )
    return result, issues


def monthly_summary(records, month):
    month_key(month)
    bills, issues = [], []
    grouped_bills = defaultdict(list)
    for r in records:
        d = r["data"]
        if d["kind"] == "bill":
            grouped_bills[(d["provider"], d["account"], d["period"], d["currency"])].append(r)
    payments, payment_issues = unique_transactions(
        [r for r in records if r["data"]["kind"] == "payment"]
    )
    issues.extend(payment_issues)
    for identity, rows in grouped_bills.items():
        if not any(r["data"]["due_on"].startswith(month) for r in rows):
            continue
        if len({(r["data"]["amount"], r["data"]["due_on"]) for r in rows}) > 1:
            issues.append(
                {
                    "reason": "Conflicting statements; review required",
                    "record_ids": [r["id"] for r in rows],
                }
            )
            continue
        r = rows[0]
        d = r["data"]
        matched = [
            p
            for p in payments
            if (
                p["data"]["provider"],
                p["data"]["account"],
                p["data"]["period"],
                p["data"]["currency"],
            )
            == identity
            and p["data"]["status"] == "credited"
            and p["data"]["occurred_on"] >= d["occurred_on"]
        ]
        paid = sum((Decimal(p["data"]["amount"]) for p in matched), Decimal(0))
        remaining = max(Decimal(0), Decimal(d["amount"]) - paid)
        bills.append(
            {
                "provider": d["provider"],
                "card": d["account"],
                "currency": d["currency"],
                "statement_amount": d["amount"],
                "due_on": d["due_on"],
                "credited": str(paid),
                "remaining_from_email": str(remaining),
                "status": "confirmed_by_email"
                if remaining == 0
                else "partial_payment"
                if paid
                else "no_confirmed_payment",
                "evidence": [
                    {"id": x["id"], "url": x["url"], "quote": x["data"]["evidence"]}
                    for x in [r, *matched]
                ],
            }
        )
    transactions, tx_issues = unique_transactions(
        [r for r in records if r["data"]["kind"] in {"charge", "refund"}]
    )
    issues.extend(tx_issues)
    totals = defaultdict(lambda: {"charges": Decimal(0), "refunds": Decimal(0)})
    subscriptions = []
    for r in transactions:
        d = r["data"]
        if (
            not d["subscription"]
            or not d["occurred_on"].startswith(month)
            or d["status"] != "credited"
        ):
            continue
        field = "charges" if d["kind"] == "charge" else "refunds"
        totals[d["currency"]][field] += Decimal(d["amount"])
        subscriptions.append({"id": r["id"], "url": r["url"], **d})
    return {
        "month": month,
        "basis": "Bills due this month; subscription charges dated this month",
        "coverage": "Accepted email evidence only. Missing emails can make totals incomplete.",
        "bills": bills,
        "subscriptions": subscriptions,
        "subscription_totals": {
            c: {**{k: str(v) for k, v in t.items()}, "net": str(t["charges"] - t["refunds"])}
            for c, t in totals.items()
        },
        "review_needed": issues,
    }
