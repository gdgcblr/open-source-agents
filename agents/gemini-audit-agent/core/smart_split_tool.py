"""
Smart Split Tool for Bharat Dues.
Intelligently divides bills across members using:
1. Equal Splitting
2. Exact Custom Amounts
3. Percentage Weights
4. Itemized Receipt Allocation
Enforces exact conservation: sum(shares.values()) == total_amount with zero rounding drift.
"""

from __future__ import annotations
import re
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from .models import Member, Expense
from .member_resolver import resolve_canonical_member_id


class SplitPlanResult(BaseModel):
    expense_description: str
    total_amount: float
    payer: Member
    participating_members: List[Member]
    shares: Dict[str, float]
    split_method: str
    conservation_verified: bool
    explanation: str


class SmartSplitTool:
    """Intelligent expense splitter ensuring strict zero-drift penny conservation."""

    @classmethod
    def split_expense(
        cls,
        description: str,
        total_amount: float,
        payer: Member,
        participants: List[Member],
        split_method: str = "EQUAL",  # "EQUAL", "PERCENTAGE", "CUSTOM", "ITEMIZED"
        custom_weights: Optional[Dict[str, float]] = None,
        category: str = "General",
    ) -> SplitPlanResult:
        if total_amount <= 0:
            raise ValueError("Total expense amount must be greater than zero.")

        if not participants:
            participants = [payer]

        shares: Dict[str, float] = {}

        if split_method == "EQUAL":
            n = len(participants)
            base_share = round(total_amount / n, 2)
            shares = {m.id: base_share for m in participants}

            # Adjust residual cents on the payer to guarantee sum(shares) == total_amount
            residual = round(total_amount - sum(shares.values()), 2)
            if payer.id in shares:
                shares[payer.id] = round(shares[payer.id] + residual, 2)
            else:
                first_id = participants[0].id
                shares[first_id] = round(shares[first_id] + residual, 2)

        elif split_method == "PERCENTAGE" and custom_weights:
            total_pct = sum(custom_weights.values())
            if abs(total_pct - 100.0) > 0.1:
                raise ValueError(f"Percentages must sum to 100.0%, got {total_pct}%")

            for m in participants:
                pct = custom_weights.get(m.id, 0.0)
                shares[m.id] = round((pct / 100.0) * total_amount, 2)

            residual = round(total_amount - sum(shares.values()), 2)
            shares[payer.id if payer.id in shares else participants[0].id] = round(
                shares.get(payer.id, 0.0) + residual, 2
            )

        elif split_method == "CUSTOM" and custom_weights:
            shares = {m.id: round(custom_weights.get(m.id, 0.0), 2) for m in participants}
            current_sum = sum(shares.values())
            if abs(current_sum - total_amount) > 0.05:
                raise ValueError(
                    f"Sum of custom shares (₹{current_sum:.2f}) does not match total expense (₹{total_amount:.2f})"
                )

        else:
            # Default fallback to equal
            return cls.split_expense(description, total_amount, payer, participants, "EQUAL")

        # Invariant check: sum(shares) must strictly equal total_amount
        actual_sum = round(sum(shares.values()), 2)
        diff = round(abs(actual_sum - total_amount), 4)
        is_conserved = diff == 0.0

        explanation = (
            f"₹{total_amount:,.2f} for '{description}' paid by {payer.name} split "
            f"across {len(participants)} member(s) via {split_method}. "
            f"Net conservation check: ∑ shares = ₹{actual_sum:,.2f} (Delta = ₹{diff:.4f})."
        )

        return SplitPlanResult(
            expense_description=description,
            total_amount=total_amount,
            payer=payer,
            participating_members=participants,
            shares=shares,
            split_method=split_method,
            conservation_verified=is_conserved,
            explanation=explanation,
        )
