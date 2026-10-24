"""
Spoke 3: Prudential Portfolio Risk & Allocation Guardrail Auditor.
Enforces SEBI prudential concentration cap (<= 25%) and 100% allocation completeness.
"""

from __future__ import annotations
from typing import Dict, Any, List
from ..models import AllocationItem
from ..invariant_guardrails import audit_invariants


class RiskGuardrailSpoke:
    name: str = "Prudential Risk & Concentration Auditor"
    urn: str = "urn:adk:spoke:arthaniti-risk-guardrail"

    @classmethod
    def execute(cls, allocations: List[Dict[str, Any]]) -> Dict[str, Any]:
        items = [
            AllocationItem(
                asset=a["asset"],
                weight_pct=float(a["weight_pct"]),
                value=float(a.get("value", 100000.0 * (float(a["weight_pct"]) / 100.0))),
            )
            for a in allocations
        ]
        report = audit_invariants(allocations=items)
        return {
            "spoke": cls.name,
            "urn": cls.urn,
            "total_weight_pct": report.weights_sum_pct,
            "is_allocation_complete": report.is_allocation_100_pct,
            "concentration_breaches": report.concentration_alerts,
            "anomalies": report.anomalies,
            "guardrail_status": report.verdict,
        }
