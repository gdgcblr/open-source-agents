"""
Spoke 4: Gemma-2-9B & Gemini 2.5 Flash Institutional Thesis Generator.
Generates structured quantitative theses based on deterministic Camarilla levels.
"""

from __future__ import annotations
from typing import Dict, Any
from ..quant_engine import calculate_quant_targets
from ..market_feed import fetch_live_quote
from ..gemma_advisor import generate_gemma_thesis


class GemmaAdvisorSpoke:
    name: str = "Gemma Institutional Thesis Generator"
    urn: str = "urn:adk:spoke:arthaniti-gemma-advisor"

    @classmethod
    def execute(cls, symbol: str, model_choice: str = "gemma-2-9b-it") -> Dict[str, Any]:
        quote = fetch_live_quote(symbol)
        targets = calculate_quant_targets(quote)
        thesis = generate_gemma_thesis(targets, model_choice=model_choice)
        return {
            "spoke": cls.name,
            "urn": cls.urn,
            "symbol": targets.symbol,
            "model_used": thesis.model,
            "bias": thesis.bias,
            "summary": thesis.summary,
            "strategic_rationale": thesis.strategic_rationale,
            "risk_factors": thesis.risk_factors,
            "suggested_action": thesis.suggested_action,
            "guardrail_status": "THESIS_SYNTHESIS_COMPLETE",
        }
