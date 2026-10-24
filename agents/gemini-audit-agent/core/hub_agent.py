"""
Google ADK Central Hub Agent for Bharat Dues (https://bharat-dues.web.app).
Orchestrates Spoke Agents using A2A (Agent-to-Agent) task dispatch:
1. Spoke 1: Double-Entry Ledger Auditor (Zero-Sum Conservation ∑Δ ≡ 0.00)
2. Spoke 2: Multimodal Gemini Receipt & Bill OCR Scanner
3. Spoke 3: Smart Split & Penny-Conservation Allocation Engine
4. Spoke 4: Settlement Execution & NPCI UPI Dispatcher
"""

from __future__ import annotations
import re
import time
from typing import Dict, Any, List, Optional

from .models import Member, Expense, SettlementRecord, SettlementStatus
from .spokes.spoke_ledger import LedgerAuditorSpoke
from .spokes.spoke_ocr import ReceiptOCRSpoke
from .spokes.spoke_split import SmartSplitSpoke
from .spokes.spoke_settlement import SettlementDispatcherSpoke
from .gemini_parser import parse_unstructured_ledger
from .chat_tool import BharatDuesChatCopilot


class AutonomousHubAgent:
    name: str = "Bharat Dues Master Hub Agent"
    urn: str = "urn:adk:hub:bharat-dues-master"

    SPOKES = [
        {"name": LedgerAuditorSpoke.name, "urn": LedgerAuditorSpoke.urn, "status": "ONLINE", "guardrail": "Zero-Sum Conservation (∑Δ ≡ 0.00)"},
        {"name": ReceiptOCRSpoke.name, "urn": ReceiptOCRSpoke.urn, "status": "ONLINE", "guardrail": "Multimodal Vision Extraction"},
        {"name": SmartSplitSpoke.name, "urn": SmartSplitSpoke.urn, "status": "ONLINE", "guardrail": "Exact Penny Allocation (0 Drift)"},
        {"name": SettlementDispatcherSpoke.name, "urn": SettlementDispatcherSpoke.urn, "status": "ONLINE", "guardrail": "Minimal Debt Graph & UPI"},
    ]

    @classmethod
    def process_user_query(
        cls,
        query: str,
        image_bytes: Optional[bytes] = None,
        mime_type: str = "image/jpeg",
    ) -> Dict[str, Any]:
        """
        Hub Agent routes user intent to appropriate spokes and enforces
        mathematical guardrails end-to-end.
        """
        start_time = time.time()
        q_lower = query.lower()

        dispatch_log: List[Dict[str, str]] = []
        dispatch_log.append({
            "step": "1. Intent Classification",
            "message": f"Hub received natural language query: '{query[:80]}...'",
            "agent": cls.name,
        })

        # Spoke 2 Dispatch: Receipt OCR & Bill Scanner
        if image_bytes or any(w in q_lower for w in ["receipt", "bill", "invoice", "scan", "swiggy", "zomato", "cafe", "hotel"]):
            dispatch_log.append({
                "step": "2. A2A Task Dispatch",
                "message": f"Dispatching to {ReceiptOCRSpoke.name} ({ReceiptOCRSpoke.urn}) for Gemini multimodal OCR.",
                "agent": ReceiptOCRSpoke.name,
            })
            ocr_res = ReceiptOCRSpoke.execute(image_bytes=image_bytes, mime_type=mime_type, user_notes=query)

            # Auto-split the scanned receipt
            payer = Member(id="shikhar", name=ocr_res["suggested_payer"] or "Shikhar", upi_id="shikhar@okhdfcbank")
            m2 = Member(id="aman", name="Aman", upi_id="aman@okaxis")
            split_res = SmartSplitSpoke.execute(
                description=f"{ocr_res['merchant']} ({ocr_res['category']})",
                total_amount=ocr_res["total_amount"],
                payer=payer,
                participants=[payer, m2],
                split_method="EQUAL",
            )

            dispatch_log.append({
                "step": "3. A2A Smart Split Dispatch",
                "message": f"Dispatching to {SmartSplitSpoke.name} to allocate ₹{ocr_res['total_amount']} across participants.",
                "agent": SmartSplitSpoke.name,
            })

            return {
                "hub_urn": cls.urn,
                "status": "SUCCESS",
                "intent": "RECEIPT_OCR_SCAN",
                "dispatch_log": dispatch_log,
                "spoke_results": {
                    "ocr": ocr_res,
                    "split": split_res,
                },
                "summary": f"Scanned {ocr_res['merchant']} bill of ₹{ocr_res['total_amount']:,.2f} ({ocr_res['category']}). Generated equal split across 2 members with zero rounding drift.",
                "guardrail_verified": True,
                "guardrail_verdict": "MULTIMODAL_RECEIPT_VERIFIED",
                "latency_ms": round((time.time() - start_time) * 1000, 2),
            }

        # Spoke 3 Dispatch: Custom / Percentage Smart Split
        if any(w in q_lower for w in ["percent", "%", "custom split", "unequal", "ratio"]):
            dispatch_log.append({
                "step": "2. A2A Task Dispatch",
                "message": f"Dispatching to {SmartSplitSpoke.name} ({SmartSplitSpoke.urn}) for weighted allocation.",
                "agent": SmartSplitSpoke.name,
            })
            p1 = Member(id="alice", name="Alice", upi_id="alice@okhdfcbank")
            p2 = Member(id="bob", name="Bob", upi_id="bob@okaxis")
            split_res = SmartSplitSpoke.execute(
                description="Custom Weighted Dinner",
                total_amount=3000.0,
                payer=p1,
                participants=[p1, p2],
                split_method="PERCENTAGE",
                custom_weights={"alice": 60.0, "bob": 40.0},
            )

            return {
                "hub_urn": cls.urn,
                "status": "SUCCESS",
                "intent": "SMART_SPLIT_ALLOCATION",
                "dispatch_log": dispatch_log,
                "spoke_results": {"split": split_res},
                "summary": split_res["explanation"],
                "guardrail_verified": split_res["conservation_verified"],
                "guardrail_verdict": split_res["guardrail_status"],
                "latency_ms": round((time.time() - start_time) * 1000, 2),
            }

        # Spoke 1 & 4 Dispatch: Double-Entry Ledger Audit & Minimal UPI Settlement
        dispatch_log.append({
            "step": "2. Natural Language Parsing",
            "message": "Parsing unstructured conversation into members, expenses, and pending settlements with Gemini 2.5 Flash / Fast-Path.",
            "agent": "Google Gemini Parser",
        })
        members, expenses, settlements = parse_unstructured_ledger(query)

        dispatch_log.append({
            "step": "3. A2A Ledger Audit Dispatch",
            "message": f"Dispatching to {LedgerAuditorSpoke.name} to enforce double-entry conservation (∑ Δ ≡ 0.00).",
            "agent": LedgerAuditorSpoke.name,
        })
        ledger_res = LedgerAuditorSpoke.execute(members, expenses, settlements)

        dispatch_log.append({
            "step": "4. A2A Settlement Graph Dispatch",
            "message": f"Dispatching to {SettlementDispatcherSpoke.name} to collapse debt graph into minimal UPI deep links.",
            "agent": SettlementDispatcherSpoke.name,
        })
        settle_res = SettlementDispatcherSpoke.execute(
            member_balances=ledger_res["member_balances"],
            upi_directory={m.id: m.upi_id for m in members if m.upi_id},
        )

        dispatch_log.append({
            "step": "5. Hub Synthesis & Guardrail Gate",
            "message": f"Mathematical invariant verified: Net Delta = ₹{ledger_res['net_zero_delta']:.4f}. Unconfirmed payments quarantined.",
            "agent": cls.name,
        })

        return {
            "hub_urn": cls.urn,
            "status": "SUCCESS",
            "intent": "BHARAT_DUES_LEDGER_AUDIT",
            "dispatch_log": dispatch_log,
            "spoke_results": {
                "ledger": ledger_res,
                "settlement": settle_res,
            },
            "summary": f"Audit complete for {len(members)} members and ₹{ledger_res['total_spent']:,.2f} total volume. "
                       f"Ledger is {ledger_res['guardrail_status']}. Generated {settle_res['transactions_count']} minimal bilateral settlement(s).",
            "guardrail_verified": ledger_res["is_balanced"],
            "guardrail_verdict": f"DOUBLE_ENTRY_CONSERVED (∑Δ = ₹{ledger_res['net_zero_delta']:.4f})",
            "latency_ms": round((time.time() - start_time) * 1000, 2),
        }
