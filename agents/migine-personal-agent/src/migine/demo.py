from datetime import date

from .models import FinancialRecord


def load_demo(store, month):
    date.fromisoformat(month + "-01")
    examples = [
        {
            "kind": "bill",
            "provider": "Example Bank",
            "account": "1234",
            "amount": "12450.00",
            "occurred_on": month + "-01",
            "due_on": month + "-20",
            "period": month,
            "status": "statement",
            "evidence": f"Statement {month}, card 1234: INR 12450.00 due {month}-20.",
        },
        {
            "kind": "payment",
            "provider": "Example Bank",
            "account": "1234",
            "amount": "12450.00",
            "occurred_on": month + "-12",
            "period": month,
            "status": "credited",
            "reference": "DEMO-P1",
            "evidence": f"INR 12450.00 credited {month}-12 to card 1234 for statement {month}. Ref DEMO-P1.",
        },
        {
            "kind": "charge",
            "provider": "Example Music",
            "amount": "149.00",
            "occurred_on": month + "-03",
            "subscription": True,
            "status": "credited",
            "reference": "DEMO-S1",
            "evidence": f"Monthly subscription charged INR 149.00 on {month}-03. Receipt DEMO-S1.",
        },
        {
            "kind": "charge",
            "provider": "Example Storage",
            "amount": "130.00",
            "occurred_on": month + "-05",
            "subscription": True,
            "status": "credited",
            "reference": "DEMO-S2",
            "evidence": f"Monthly subscription charged INR 130.00 on {month}-05. Receipt DEMO-S2.",
        },
    ]
    for index, data in enumerate(examples):
        record = FinancialRecord(currency="INR", **data)
        source_id = f"demo-{month}-{index}"
        store.add_source(
            {
                "id": source_id,
                "title": "SYNTHETIC: " + data["kind"],
                "body": data["evidence"],
                "received": data["occurred_on"],
                "url": "demo:" + source_id,
            }
        )
        key = store.add_record(source_id, record)
        with store.connect() as db:
            db.execute("UPDATE records SET review='accepted' WHERE id=?", (key,))
    return {"demo": True, "month": month, "records": len(examples)}
