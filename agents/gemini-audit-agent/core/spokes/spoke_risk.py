"""
Spoke 3: Portfolio Health & Allocation Guardrails.
Enforces prudential risk concentration limits (<= 25.0%),
capital allocation completeness (100.00%), and Herfindahl-Hirschman Index (HHI).
"""

from __future__ import annotations
from typing import List, Dict, Any


class PortfolioRiskSpoke:
    name: str = "Portfolio Health & Concentration Auditor"
    urn: str = "urn:adk:spoke:portfolio-risk"

    @classmethod
    def execute(
        cls,
        allocations: List[Dict[str, Any]],
        max_single_weight_pct: float = 25.0,
    ) -> Dict[str, Any]:
        total_weight = sum(item.get("weight_pct", 0.0) for item in allocations)
        total_weight = round(total_weight, 2)

        is_complete = abs(total_weight - 100.0) <= 0.01

        breaches = []
        hhi = 0.0
        for item in allocations:
            w = item.get("weight_pct", 0.0)
            asset = item.get("asset", "Unknown")
            hhi += (w / 100.0) ** 2
            if w > max_single_weight_pct:
                breaches.append({
                    "asset": asset,
                    "weight_pct": w,
                    "excess_pct": round(w - max_single_weight_pct, 2),
                    "action_required": f"Trim {round(w - max_single_weight_pct, 2)}% to restore safe 25% prudential cap.",
                })

        hhi = round(hhi, 4)
        diversification_status = "OPTIMAL_DIVERSIFICATION" if hhi < 0.18 else "CONCENTRATED_EXPOSURE"

        return {
            "spoke": cls.name,
            "urn": cls.urn,
            "total_weight_pct": total_weight,
            "is_allocation_complete": is_complete,
            "hhi_index": hhi,
            "diversification_status": diversification_status,
            "concentration_breaches": breaches,
            "guardrail_status": "PASSED" if (is_complete and not breaches) else "TRIGGERED_REBALANCING_DIRECTIVE",
        }
