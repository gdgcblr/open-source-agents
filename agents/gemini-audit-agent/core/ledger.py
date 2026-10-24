"""Double-Entry Mathematical Ledger & Invariant Audit Engine.

Enforces:
1. Double-Entry Balance Conservation: sum(balances) == 0.00
2. Pending Settlement Isolation: unconfirmed payments do not corrupt confirmed balances
3. Anomaly Detection: identifies floating point drift, ID fragmentation, and unbalanced splits
4. Greedy Bilateral Simplification: optimal cash settlement paths
"""
from __future__ import annotations
from typing import Dict, List, Tuple
from .models import (
    Member,
    Expense,
    SettlementRecord,
    SettlementStatus,
    SettlementTransaction,
    AuditAnomaly,
    AuditReport,
)
from .member_resolver import build_canonical_member_index, resolve_canonical_member_id


def compute_member_balances(
    members: List[Member],
    expenses: List[Expense],
    settlements: List[SettlementRecord],
) -> Dict[str, float]:
    """Computes the net balance for every member across all expenses and confirmed settlements.
    
    Positive (>0): Member is owed money (creditor).
    Negative (<0): Member owes money (debtor).
    Zero (==0): Member is settled.
    """
    index = build_canonical_member_index(members)
    balances: Dict[str, float] = {m.id: 0.0 for m in members}

    # 1. Process Expenses
    for expense in expenses:
        canon_payer = resolve_canonical_member_id(expense.payer_id, members, index)
        if canon_payer not in balances:
            balances[canon_payer] = 0.0
        balances[canon_payer] += expense.amount

        for member_id, share in expense.shares.items():
            canon_share = resolve_canonical_member_id(member_id, members, index)
            if canon_share not in balances:
                balances[canon_share] = 0.0
            balances[canon_share] -= share

    # 2. Process Settlements (ONLY confirmed settlements affect ledger balances)
    for s in settlements:
        if s.status == SettlementStatus.confirmed:
            canon_from = resolve_canonical_member_id(s.from_member_id, members, index)
            canon_to = resolve_canonical_member_id(s.to_member_id, members, index)
            if canon_from not in balances:
                balances[canon_from] = 0.0
            if canon_to not in balances:
                balances[canon_to] = 0.0
            balances[canon_from] += s.amount
            balances[canon_to] -= s.amount

    # 3. Precision Guardrail: Clean floating point noise (-0.0 -> 0.0)
    for k in list(balances.keys()):
        val = balances[k]
        if abs(val) < 0.005:
            balances[k] = 0.0
        else:
            balances[k] = round(val, 2)

    return balances


def settle_balances(
    members: List[Member],
    balances: Dict[str, float],
) -> List[SettlementTransaction]:
    """Computes the minimal bilateral transactions to settle all debts (Greedy match)."""
    index = build_canonical_member_index(members)
    member_map = {m.id: m for m in members}

    # Pre-fold into canonical IDs
    folded: Dict[str, float] = {}
    for raw_id, val in balances.items():
        canon = resolve_canonical_member_id(raw_id, members, index)
        folded[canon] = folded.get(canon, 0.0) + val

    debtors: List[List] = []  # [id, amount_owed]
    creditors: List[List] = []  # [id, amount_to_receive]

    for m_id, net in folded.items():
        rounded = round(net, 2)
        if rounded < -0.005:
            debtors.append([m_id, abs(rounded)])
        elif rounded > 0.005:
            creditors.append([m_id, rounded])

    debtors.sort(key=lambda x: x[1], reverse=True)
    creditors.sort(key=lambda x: x[1], reverse=True)

    transactions: List[SettlementTransaction] = []
    d_idx = 0
    c_idx = 0

    while d_idx < len(debtors) and c_idx < len(creditors):
        d = debtors[d_idx]
        c = creditors[c_idx]

        settle_amt = round(min(d[1], c[1]), 2)
        if settle_amt > 0.005:
            from_m = member_map.get(d[0], Member(id=d[0], name=d[0]))
            to_m = member_map.get(c[0], Member(id=c[0], name=c[0]))

            transactions.append(
                SettlementTransaction(
                    from_member_id=from_m.id,
                    from_name=from_m.name,
                    to_member_id=to_m.id,
                    to_name=to_m.name,
                    amount=settle_amt,
                    payee_upi_id=to_m.upi_id,
                    payee_phone=to_m.phone_number,
                )
            )

        d[1] -= settle_amt
        c[1] -= settle_amt

        if d[1] < 0.005:
            d_idx += 1
        if c[1] < 0.005:
            c_idx += 1

    return transactions


def audit_ledger(
    members: List[Member],
    expenses: List[Expense],
    settlements: List[SettlementRecord],
) -> AuditReport:
    """Performs a comprehensive financial and structural audit of the ledger."""
    anomalies: List[AuditAnomaly] = []
    index = build_canonical_member_index(members)

    # 1. Total spent
    total_spent = round(sum(e.amount for e in expenses), 2)

    # 2. Check each expense split equality
    for e in expenses:
        share_sum = round(sum(e.shares.values()), 2)
        if abs(share_sum - e.amount) > 0.01:
            anomalies.append(
                AuditAnomaly(
                    type="SPLIT_MISMATCH",
                    description=f"Expense '{e.description}' total ({e.amount}) does not match sum of shares ({share_sum}).",
                    severity="HIGH",
                    suggested_fix="Re-split remainder cents evenly across included members.",
                )
            )

    # 3. Check for ID fragmentation
    member_ids = {m.id for m in members}
    used_ids = set()
    for e in expenses:
        used_ids.add(e.payer_id)
        used_ids.update(e.shares.keys())
    for s in settlements:
        used_ids.add(s.from_member_id)
        used_ids.add(s.to_member_id)

    fragmented_ids = [uid for uid in used_ids if uid not in member_ids]
    if fragmented_ids:
        anomalies.append(
            AuditAnomaly(
                type="ID_FRAGMENTATION",
                description=f"Found {len(fragmented_ids)} alias identifiers (e.g. {fragmented_ids[:3]}) resolved via canonical index.",
                severity="MEDIUM",
                suggested_fix="Normalize all records to canonical Member.id before persistence.",
            )
        )

    # 4. Check Pending settlements
    pending = [s for s in settlements if s.status == SettlementStatus.pending]
    if pending:
        anomalies.append(
            AuditAnomaly(
                type="PENDING_HOLD",
                description=f"{len(pending)} unverified payment(s) total ₹{sum(p.amount for p in pending):.2f} awaiting recipient confirmation.",
                severity="LOW",
                suggested_fix="Notify recipient to verify receipt via UPI/Bank confirmation.",
            )
        )

    # 5. Compute balances
    balances = compute_member_balances(members, expenses, settlements)

    # 6. Check conservation invariant: sum(balances) == 0.00
    net_zero = round(sum(balances.values()), 4)
    is_balanced = abs(net_zero) < 0.01

    if not is_balanced:
        anomalies.append(
            AuditAnomaly(
                type="BALANCE_DRIFT",
                description=f"Mathematical conservation violated! Net sum of balances is {net_zero} (expected 0.00).",
                severity="HIGH",
                suggested_fix="Re-derive ledger from journals and adjust rounding cents.",
            )
        )

    optimal_txs = settle_balances(members, balances)

    return AuditReport(
        is_balanced=is_balanced,
        total_spent=total_spent,
        member_balances=balances,
        net_zero_delta=net_zero,
        anomalies=anomalies,
        optimal_settlements=optimal_txs,
        pending_settlements_count=len(pending),
    )
