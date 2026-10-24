"""
Spoke 1: Bharat Dues Double-Entry Ledger & Receipt Auditor.
Enforces net zero-sum mathematical conservation (∑ Δ ≡ 0.00),
isolates pending unapproved settlements, and normalizes member identities via O(1) hash indexing.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
from ..models import Member, Expense, SettlementRecord, AuditReport
from ..ledger import audit_ledger


class LedgerAuditorSpoke:
    name: str = "Bharat Dues Ledger Auditor"
    urn: str = "urn:adk:spoke:bharat-dues-ledger"

    @classmethod
    def execute(
        cls,
        members: List[Member],
        expenses: List[Expense],
        settlements: Optional[List[SettlementRecord]] = None,
    ) -> Dict[str, Any]:
        report: AuditReport = audit_ledger(
            members=members,
            expenses=expenses,
            settlements=settlements or [],
        )

        return {
            "spoke": cls.name,
            "urn": cls.urn,
            "is_balanced": report.is_balanced,
            "net_zero_delta": report.net_zero_delta,
            "total_spent": report.total_spent,
            "pending_count": report.pending_settlements_count,
            "member_balances": report.member_balances,
            "anomalies": [a.description for a in report.anomalies],
            "settlements_required": [
                {
                    "from_member_id": s.from_member_id,
                    "from_name": s.from_name,
                    "to_member_id": s.to_member_id,
                    "to_name": s.to_name,
                    "amount": s.amount,
                    "payee_upi_id": s.payee_upi_id,
                    "payee_phone": s.payee_phone,
                }
                for s in report.optimal_settlements
            ],
            "guardrail_status": "CONSERVED (∑ Δ = 0.00)" if report.is_balanced else "BREACH DETECTED",
        }
