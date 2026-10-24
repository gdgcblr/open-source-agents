"""Guess which department a sheet belongs to from its tab name and column headers."""
from __future__ import annotations

import pandas as pd

KEYWORDS: dict[str, tuple[str, ...]] = {
    "Sales": ("sales", "invoice", "customer", "revenue", "qty", "quantity"),
    "Inventory": ("inventory", "stock", "sku", "reorder", "warehouse", "item"),
    "Finance": ("finance", "expense", "payment", "ledger", "receivable", "payable", "balance", "amount due"),
    "Support": ("support", "ticket", "complaint", "issue", "resolution"),
    "HR": ("hr", "employee", "leave", "attendance", "salary", "payroll"),
    "Operations": ("order", "activity", "dispatch", "timestamp", "event", "delivery", "shipment"),
}


def classify(sheet_name: str, df: pd.DataFrame) -> dict:
    name = sheet_name.lower()
    headers = " ".join(str(c).lower() for c in df.columns)
    scores: dict[str, int] = {}
    for dept, words in KEYWORDS.items():
        # tab name counts triple: owners usually name tabs well
        scores[dept] = sum(3 for w in words if w in name) + sum(1 for w in words if w in headers)
    best = max(scores, key=scores.get)
    top = scores[best]
    if top == 0:
        return {"department": "Unknown", "confidence": "low", "ask_owner": True}
    runner_up = sorted(scores.values())[-2]
    confidence = "high" if top >= runner_up + 3 else "medium" if top > runner_up else "low"
    return {"department": best, "confidence": confidence, "ask_owner": confidence == "low"}
