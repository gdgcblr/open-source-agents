"""Deterministic FAQ helper for web demo (no LLM required)."""

from __future__ import annotations


def answer_question(question: str) -> dict[str, str]:
    q = question.lower().strip()
    if not q:
        return {
            "answer": "Ask about deposits, red flags, rent estimates, or Karnataka checklist items.",
            "source": "rentrakshak_helper",
        }
    if "deposit" in q and ("limit" in q or "maximum" in q or "cap" in q):
        return {
            "answer": (
                "There is no universal Karnataka deposit cap in RentRakshak's sourced guidance. "
                "Read your agreement and verify terms in writing before paying."
            ),
            "source": "checklist_tool",
        }
    if "otp" in q or "scam" in q or "fraud" in q:
        return {
            "answer": (
                "Never share OTPs or passwords. Use Analyze Listing for rule-based checks (RF-005, payment pressure). "
                "Visit the property before paying token money."
            ),
            "source": "risk_rules",
        }
    if "rent" in q and ("koramangala" in q or "whitefield" in q or "hsr" in q):
        return {
            "answer": "Open Rent Estimates, pick a locality card, then refine BHK/furnishing for a transparent range from our demo JSON dataset.",
            "source": "rent_estimator",
        }
    if "checklist" in q or "agreement" in q:
        return {
            "answer": "See Rental Checklist for viewing, deposit refund, notice period, and stamp-duty questions flagged as needs clarification.",
            "source": "checklist",
        }
    return {
        "answer": (
            "For full analysis use **Analyze Listing** or run `adk web adk_agent` with Gemini/Ollama. "
            "I only provide quick deterministic hints in this demo."
        ),
        "source": "fallback",
    }
