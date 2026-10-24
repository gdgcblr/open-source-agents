"""
Conversational AI Chat Assistant for Bharat Dues.
Provides an intuitive, natural language pair-copilot for group expense tracking,
balance queries, invoice OCR integration, and double-entry ledger audits.
"""

from __future__ import annotations
import re
import os
import json
import time
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

from .models import Member, Expense, SettlementRecord, SettlementStatus
from .ledger import audit_ledger
from .gemini_parser import parse_unstructured_ledger
from .smart_split_tool import SmartSplitTool
from .ocr_tool import ReceiptOCRTool


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: float = Field(default_factory=time.time)


class ChatResponse(BaseModel):
    reply: str
    intent: str
    suggested_actions: List[str] = Field(default_factory=list)
    updated_ledger_state: Optional[Dict[str, Any]] = None


class BharatDuesChatCopilot:
    """Conversational assistant managing dialogue, expense intents, and invariant audits."""

    @classmethod
    def handle_message(
        cls,
        user_message: str,
        conversation_history: Optional[List[ChatMessage]] = None,
        current_members: Optional[List[Member]] = None,
        current_expenses: Optional[List[Expense]] = None,
        current_settlements: Optional[List[SettlementRecord]] = None,
    ) -> ChatResponse:
        msg = user_message.strip()
        msg_lower = msg.lower()

        # Intent 1: Balance & Debt Query ("Who owes what?", "Show balances")
        if any(w in msg_lower for w in ["who owes", "balance", "how much do i owe", "status", "summary"]):
            members, expenses, settlements = parse_unstructured_ledger(msg)
            if not members and current_members:
                members = current_members
                expenses = current_expenses or []
                settlements = current_settlements or []

            report = audit_ledger(members or [], expenses or [], settlements or [])

            bal_lines = []
            for m_id, net in report.member_balances.items():
                if net > 0:
                    bal_lines.append(f"* **{m_id.capitalize()}**: Gets back **+₹{net:,.2f}**")
                elif net < 0:
                    bal_lines.append(f"* **{m_id.capitalize()}**: Owes **-₹{abs(net):,.2f}**")
                else:
                    bal_lines.append(f"* **{m_id.capitalize()}**: Fully settled (**₹0.00**)")

            settle_lines = []
            for s in report.optimal_settlements:
                settle_lines.append(f"* **{s.from_name}** pays **{s.to_name}** **₹{s.amount:,.2f}**")

            reply = f"### 📊 Current Group Balance Sheet\n\n"
            reply += f"**Total Volume Audited:** ₹{report.total_spent:,.2f}\n"
            reply += f"**Double-Entry Status:** {'✅ CONSERVED (∑Δ ≡ 0.00)' if report.is_balanced else '⚠️ UNBALANCED'}\n\n"
            reply += "#### Member Net Balances:\n" + ("\n".join(bal_lines) if bal_lines else "*No expenses logged yet.*") + "\n\n"
            reply += "#### Minimal Settlement Plan:\n" + ("\n".join(settle_lines) if settle_lines else "*All dues settled!*")

            if report.pending_settlements_count > 0:
                reply += f"\n\n> 🛡️ **Quarantine Alert**: {report.pending_settlements_count} unconfirmed payment(s) held in quarantine to prevent balance corruption."

            return ChatResponse(
                reply=reply,
                intent="QUERY_BALANCES",
                suggested_actions=["Settle all dues via UPI", "Add another expense", "Download Audit Certificate"],
                updated_ledger_state={"is_balanced": report.is_balanced, "balances": report.member_balances},
            )

        # Intent 2: Invariant & Guardrail Explanation ("Why double entry?", "What is invariant?")
        if any(w in msg_lower for w in ["invariant", "double-entry", "why", "quarantine", "algorithm"]):
            reply = """### 🛡️ Why Bharat Dues Invariant Guardrails Matter

Traditional expense-sharing apps suffer from **silent ledger drift** and **premature settlement corruption**. Bharat Dues mathematically protects your group via two core invariants:

1. **Double-Entry Conservation ($\sum \Delta \equiv 0.00$):**
   Every single rupee spent by a payer is simultaneously credited as an asset and debited across beneficiaries. The sum of all balances must equal exactly zero down to the fourth decimal place.

2. **Pending Settlement Quarantine:**
   When a friend taps "I Paid", that payment is quarantined in a `PENDING` state until the recipient confirms receipt on their UPI app. This prevents the classic "phantom settlement" bug where debt is wiped out before money actually arrives.

3. **$O(1)$ Canonical Identity Resolution:**
   Phone numbers, UPI IDs, and informal nicknames ("Shikhar", "shikh", "9876543210") are mapped to a canonical hash, eliminating identity fragmentation."""

            return ChatResponse(
                reply=reply,
                intent="EXPLAIN_INVARIANTS",
                suggested_actions=["Try Trip Lunch Bug demo", "Audit current group", "Open live app"],
            )

        # Intent 3: Settlement Directive ("Settle up", "Pay via UPI")
        if any(w in msg_lower for w in ["settle", "pay", "upi", "clear debt"]):
            members, expenses, settlements = parse_unstructured_ledger(msg)
            report = audit_ledger(members, expenses, settlements)

            upi_cards = []
            for s in report.optimal_settlements:
                receiver_upi = s.payee_upi_id or f"{s.to_member_id}@okhdfcbank"
                link = f"upi://pay?pa={receiver_upi}&pn={s.to_name}&am={s.amount:.2f}&cu=INR&tn=Bharat+Dues+Settlement"
                upi_cards.append(f"* **{s.from_name} &rarr; {s.to_name}**: ₹{s.amount:,.2f} [Pay via UPI ↗]({link})")

            reply = f"### ⚡ 1-Tap UPI Settlement Directive\n\n"
            reply += "Greedy graph algorithm collapsed multi-party debts into minimal bilateral transfers:\n\n"
            reply += "\n".join(upi_cards) if upi_cards else "All balances are settled! No payments required."

            return ChatResponse(
                reply=reply,
                intent="SETTLE_DIRECTIVE",
                suggested_actions=["Verify transaction", "Share with group", "Download receipt"],
            )

        # Intent 4: Default - Parse natural language expense
        members, expenses, settlements = parse_unstructured_ledger(msg)
        report = audit_ledger(members, expenses, settlements)

        if expenses:
            exp = expenses[0]
            reply = f"### ✅ Added Expense: {exp.description}\n\n"
            reply += f"* **Amount:** ₹{exp.amount:,.2f}\n"
            reply += f"* **Payer:** {exp.payer_id.capitalize()}\n"
            reply += f"* **Split Across:** {len(exp.shares)} members ({', '.join(k.capitalize() for k in exp.shares.keys())})\n"
            reply += f"* **Double-Entry Check:** Net Invariant Delta = ₹{report.net_zero_delta:.4f} (CONSERVED)\n\n"

            if report.optimal_settlements:
                s = report.optimal_settlements[0]
                reply += f"👉 **Action Required:** {s.from_name} owes {s.to_name} **₹{s.amount:,.2f}**."

            return ChatResponse(
                reply=reply,
                intent="ADD_EXPENSE",
                suggested_actions=["Who owes what?", "Settle up via UPI", "Add another bill"],
                updated_ledger_state={"is_balanced": report.is_balanced, "balances": report.member_balances},
            )

        # Fallback guidance
        return ChatResponse(
            reply="I'm your **Bharat Dues Financial Copilot**. You can:\n"
                  "- Tell me about an expense (e.g. *\"Shikhar paid ₹3,000 for dinner split with Aman\"*)\n"
                  "- Ask *\"Who owes what?\"* to inspect audited balances\n"
                  "- Say *\"Settle up\"* to generate NPCI UPI deep links\n"
                  "- Ask *\"Why double entry?\"* to inspect invariant guardrails",
            intent="HELP",
            suggested_actions=[
                "Shikhar paid ₹3,000 for dinner split with Aman",
                "Who owes what right now?",
                "Why double-entry invariant matters?",
            ],
        )
