"""
Spoke 5: High-Conviction Quant Screener Engine.
Screens equities for Camarilla breakout setups, near 52-week highs, and high momentum breadth.
"""

from __future__ import annotations
from typing import Dict, Any, List
from ..screener_engine import screen_stocks


class ScreenerSpoke:
    name: str = "Quantitative Equity Screener"
    urn: str = "urn:adk:spoke:arthaniti-screener"

    @classmethod
    def execute(cls, filter_mode: str = "ALL") -> Dict[str, Any]:
        preset = "momentum_breakout" if "momentum" in filter_mode.lower() or "breakout" in filter_mode.lower() else "undervalued_quality"
        results = screen_stocks(preset=preset)
        return {
            "spoke": cls.name,
            "urn": cls.urn,
            "filter_mode": filter_mode,
            "preset": preset,
            "matches_count": len(results),
            "matches": [r.model_dump() for r in results],
            "guardrail_status": "SCREENER_EXECUTION_COMPLETE",
        }
