"""
Spoke 1: Realtime NSE/BSE Market Feed & Gemma Symbol Resolver.
Auto-resolves company names / aliases to live trading symbols with in-memory caching.
"""

from __future__ import annotations
from typing import Dict, Any
from ..symbol_resolver import resolve_smart_ticker
from ..market_feed import fetch_live_quote


class MarketFeedSpoke:
    name: str = "Realtime Market Feed & Symbol Resolver"
    urn: str = "urn:adk:spoke:arthaniti-market-feed"

    @classmethod
    def execute(cls, query: str) -> Dict[str, Any]:
        resolved, method = resolve_smart_ticker(query)
        quote = fetch_live_quote(resolved)
        return {
            "spoke": cls.name,
            "urn": cls.urn,
            "raw_query": query,
            "resolved_symbol": quote.symbol,
            "resolution_method": method,
            "ltp": quote.ltp,
            "high": quote.high,
            "low": quote.low,
            "close": quote.close,
            "change_pct": quote.change_pct,
            "volume": quote.volume,
            "high52": quote.high52,
            "low52": quote.low52,
            "guardrail_status": "FEED_VERIFIED",
        }
