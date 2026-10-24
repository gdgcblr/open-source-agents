"""
Financial Invariant Guardrails & Precision Auditing Engine.
Extracted from SettleUp Lite double-entry ledger invariants and DalalDesk portfolio limits.
Guarantees zero-sum balance, allocation completeness, precision rounding, and concentration safeguards.
"""

from __future__ import annotations
from typing import List, Optional
from core.models import LedgerEntry, AllocationItem, InvariantAuditReport


def audit_invariants(
    entries: Optional[List[LedgerEntry]] = None,
    allocations: Optional[List[AllocationItem]] = None,
    max_single_weight_pct: float = 25.0,
    tolerance: float = 0.01,
) -> InvariantAuditReport:
    """
    Evaluates financial invariant rules across ledger entries and portfolio allocations.
    """
    entries = entries or []
    allocations = allocations or []

    anomalies: List[str] = []
    concentration_alerts: List[str] = []

    # 1. Double-entry Zero-Sum Check: sum(amounts) == 0.0
    total_delta = 0.0
    for e in entries:
        total_delta += e.amount
    total_delta = round(total_delta, 4)

    is_zero_sum = abs(total_delta) <= tolerance
    if not is_zero_sum and entries:
        anomalies.append(
            f"Zero-Sum Invariant Violation: Net delta is ₹{total_delta:+.2f} (expected ₹0.00). Ledger is unbalanced."
        )

    # 2. Portfolio Allocation Sum: sum(weights) == 100.0%
    weights_sum = 0.0
    for item in allocations:
        weights_sum += item.weight_pct
    weights_sum = round(weights_sum, 2)

    is_alloc_100 = True
    if allocations:
        is_alloc_100 = abs(weights_sum - 100.0) <= tolerance
        if not is_alloc_100:
            anomalies.append(
                f"Allocation Invariant Violation: Total portfolio weight is {weights_sum:.2f}% (must sum to exactly 100.00%)."
            )

    # 3. Concentration Guardrails
    for item in allocations:
        if item.weight_pct > max_single_weight_pct:
            concentration_alerts.append(
                f"Concentration Breach: Asset '{item.asset}' has {item.weight_pct:.1f}% weight (exceeds limit of {max_single_weight_pct}%)."
            )

    # 4. Floating-point precision drift check
    drift_detected = False
    for e in entries:
        rounded = round(e.amount, 2)
        if abs(e.amount - rounded) > 0.0001:
            drift_detected = True
            anomalies.append(f"Precision Drift Detected: Amount {e.amount} has unrounded fractional sub-cents.")
            break

    # Final Status
    status = "PASSED" if (is_zero_sum and is_alloc_100 and not drift_detected) else "FAILED"
    verdict = (
        "AUDIT PASSED: All financial invariants strictly verified."
        if status == "PASSED"
        else f"AUDIT FAILED: {len(anomalies)} invariant violation(s) detected."
    )

    return InvariantAuditReport(
        status=status,
        total_delta=round(total_delta, 2),
        is_zero_sum_balanced=is_zero_sum,
        weights_sum_pct=weights_sum,
        is_allocation_100_pct=is_alloc_100,
        drift_detected=drift_detected,
        concentration_alerts=concentration_alerts,
        anomalies=anomalies,
        verdict=verdict,
    )
