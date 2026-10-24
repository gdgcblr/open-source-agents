"""Ledger invariants (TECHNICAL_SCOPING.md §5). Checked inside every write
transaction; any violation rolls the transaction back."""

import sqlite3
from datetime import date

from ledger.config import LedgerConfig

_SETTLED = """
SELECT i.id, i.amount_paise, i.hold,
       COALESCE(SUM(a.paid_paise + a.tds_paise), 0) AS settled
FROM invoices i LEFT JOIN allocations a ON a.invoice_id = i.id
GROUP BY i.id
"""


def check(conn: sqlite3.Connection, config: LedgerConfig) -> list[str]:
    tol = config.tolerance_paise
    violations: list[str] = []
    invoices = {r["id"]: r for r in conn.execute(_SETTLED)}

    # I1: never settle more than the invoice amount
    for inv in invoices.values():
        if inv["settled"] > inv["amount_paise"] + tol:
            violations.append(f"I1 {inv['id']}: settled {inv['settled']} > amount {inv['amount_paise']}")

    # I3 + I7: pending reminders only for open invoices, at the current outstanding amount
    for r in conn.execute("SELECT id, invoice_id, amount_due_paise FROM reminders "
                          "WHERE status IN ('QUEUED', 'APPROVED')"):
        inv = invoices[r["invoice_id"]]
        outstanding = inv["amount_paise"] - inv["settled"]
        if inv["hold"] or outstanding <= tol:
            violations.append(f"I3 reminder {r['id']}: pending for closed invoice {r['invoice_id']}")
        elif r["amount_due_paise"] != outstanding:
            violations.append(f"I7 reminder {r['id']}: amount {r['amount_due_paise']} != outstanding {outstanding}")

    # I5: no two sent reminders for one invoice inside the cooldown window
    sent: dict[str, list[date]] = {}
    for r in conn.execute("SELECT invoice_id, sent_on FROM reminders WHERE sent_on IS NOT NULL "
                          "ORDER BY sent_on"):
        sent.setdefault(r["invoice_id"], []).append(date.fromisoformat(r["sent_on"]))
    for inv_id, dates in sent.items():
        for a, b in zip(dates, dates[1:]):
            if (b - a).days < config.cooldown_days:
                violations.append(f"I5 {inv_id}: reminders sent {a} and {b} within cooldown")

    # I6: a payment is never allocated beyond its own amount
    for p in conn.execute("""
        SELECT p.id, p.amount_paise, COUNT(a.id) AS n, COALESCE(SUM(a.paid_paise), 0) AS used
        FROM payments p LEFT JOIN allocations a ON a.payment_id = p.id GROUP BY p.id"""):
        if p["used"] > p["amount_paise"] + tol * max(p["n"], 1):
            violations.append(f"I6 payment {p['id']}: allocated {p['used']} > amount {p['amount_paise']}")
        # I9: MATCHED <=> has allocations
        status = conn.execute("SELECT status FROM payments WHERE id = ?", (p["id"],)).fetchone()[0]
        if (status == "MATCHED") != (p["n"] > 0):
            violations.append(f"I9 payment {p['id']}: status {status} with {p['n']} allocations")

    # I8: every allocation, proposal and reminder has an audit event
    for table, entity in (("allocations", "allocation"), ("match_proposals", "match_proposal"),
                          ("reminders", "reminder")):
        missing = conn.execute(f"""
            SELECT t.id FROM {table} t WHERE NOT EXISTS (
              SELECT 1 FROM audit a WHERE a.entity = ? AND a.entity_id = CAST(t.id AS TEXT))""",
                               (entity,)).fetchall()
        for row in missing:
            violations.append(f"I8 {entity} {row[0]}: no audit event")

    return violations
