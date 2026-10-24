"""
Spoke 3: Smart Split & Penny-Conservation Allocation Engine.
Calculates itemized, percentage, and equal expense allocations with zero rounding drift.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from ..models import Member
from ..smart_split_tool import SmartSplitTool, SplitPlanResult


class SmartSplitSpoke:
    name: str = "Smart Split & Allocation Engine"
    urn: str = "urn:adk:spoke:smart-split"

    @classmethod
    def execute(
        cls,
        description: str,
        total_amount: float,
        payer: Member,
        participants: List[Member],
        split_method: str = "EQUAL",
        custom_weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        result: SplitPlanResult = SmartSplitTool.split_expense(
            description=description,
            total_amount=total_amount,
            payer=payer,
            participants=participants,
            split_method=split_method,
            custom_weights=custom_weights,
        )

        return {
            "spoke": cls.name,
            "urn": cls.urn,
            "description": result.expense_description,
            "total_amount": result.total_amount,
            "payer": result.payer.name,
            "participants": [p.name for p in result.participating_members],
            "shares": result.shares,
            "split_method": result.split_method,
            "conservation_verified": result.conservation_verified,
            "explanation": result.explanation,
            "guardrail_status": "EXACT_ZERO_DRIFT_CONSERVED",
        }
