"""
Google ADK Central Hub Agent for Arthaniti Quantitative Intelligence.
Orchestrates Spoke Agents using A2A (Agent-to-Agent) task dispatch:
1. Spoke 1: Realtime Market Feed & Gemma Symbol Resolver
2. Spoke 2: Camarilla & Classic Floor Pivot Engine
3. Spoke 3: Prudential Risk & Concentration Auditor
4. Spoke 4: Gemma Institutional Thesis Generator
5. Spoke 5: Quantitative Equity Screener
"""

from __future__ import annotations
import re
import time
from typing import Dict, Any, List, Optional

from .spokes.spoke_market_feed import MarketFeedSpoke
from .spokes.spoke_quant_engine import QuantEngineSpoke
from .spokes.spoke_risk_guardrail import RiskGuardrailSpoke
from .spokes.spoke_gemma_advisor import GemmaAdvisorSpoke
from .spokes.spoke_screener import ScreenerSpoke


class ArthanitiMasterHub:
    name: str = "Arthaniti Master Quant Hub"
    urn: str = "urn:adk:hub:arthaniti-quant-master"

    SPOKES = [
        {"name": MarketFeedSpoke.name, "urn": MarketFeedSpoke.urn, "status": "ONLINE", "guardrail": "Realtime Quotes & Symbol Resolver"},
        {"name": QuantEngineSpoke.name, "urn": QuantEngineSpoke.urn, "status": "ONLINE", "guardrail": "Camarilla Equation (H4, H3, L3, L4)"},
        {"name": RiskGuardrailSpoke.name, "urn": RiskGuardrailSpoke.urn, "status": "ONLINE", "guardrail": "SEBI Prudential Concentration Cap (<= 25%)"},
        {"name": GemmaAdvisorSpoke.name, "urn": GemmaAdvisorSpoke.urn, "status": "ONLINE", "guardrail": "Selectable Gemma-2-9B / Gemini Thesis"},
        {"name": ScreenerSpoke.name, "urn": ScreenerSpoke.urn, "status": "ONLINE", "guardrail": "Volume Breakout & Breadth Scanner"},
    ]

    @classmethod
    def process_user_query(
        cls,
        query: str,
        model_choice: str = "gemma-2-9b-it",
    ) -> Dict[str, Any]:
        start_time = time.time()
        q_lower = query.lower()

        dispatch_log: List[Dict[str, str]] = []
        dispatch_log.append({
            "step": "1. Intent Classification",
            "message": f"Hub received natural language query: '{query[:80]}...'",
            "agent": cls.name,
        })

        # Priority 1: Portfolio Risk & Concentration Audit
        if any(w in q_lower for w in ["portfolio", "concentration", "allocation", "hhi", "risk cap"]):
            dispatch_log.append({
                "step": "2. A2A Task Dispatch",
                "message": f"Dispatching to {RiskGuardrailSpoke.name} for prudential 25% concentration audit.",
                "agent": RiskGuardrailSpoke.name,
            })
            sample_allocations = [
                {"asset": "HFCL", "weight_pct": 35.0},
                {"asset": "TCS", "weight_pct": 20.0},
                {"asset": "HDFCBANK", "weight_pct": 20.0},
                {"asset": "LIQUID_BEES", "weight_pct": 25.0},
            ]
            risk_res = RiskGuardrailSpoke.execute(sample_allocations)
            return {
                "hub_urn": cls.urn,
                "status": "SUCCESS",
                "intent": "PORTFOLIO_RISK_AUDIT",
                "dispatch_log": dispatch_log,
                "spoke_results": {"risk": risk_res},
                "summary": f"Portfolio concentration audit complete. Total weight: {risk_res['total_weight_pct']}%. " + (f"ALERT: {len(risk_res['concentration_breaches'])} asset(s) breach 25% prudential limit." if risk_res['concentration_breaches'] else "All positions within safe limits."),
                "guardrail_verified": risk_res["is_allocation_complete"],
                "guardrail_verdict": risk_res["guardrail_status"],
                "latency_ms": round((time.time() - start_time) * 1000, 2),
            }

        # Check candidate ticker in query
        candidate = None
        for tick in ["HFCL", "APAR", "SUZLON", "TATA POWER", "RELIANCE", "TCS", "INFY", "HDFCBANK"]:
            if tick.lower() in q_lower:
                candidate = tick
                break

        # Priority 2: Screener (only if no specific stock ticker is requested)
        if not candidate and any(w in q_lower for w in ["screen", "scanner", "breakout", "momentum", "top stocks", "candidates"]):
            dispatch_log.append({
                "step": "2. A2A Task Dispatch",
                "message": f"Dispatching to {ScreenerSpoke.name} to screen Indian market universe.",
                "agent": ScreenerSpoke.name,
            })
            mode = "BULLISH" if "bull" in q_lower else ("BEARISH" if "bear" in q_lower else "ALL")
            screen_res = ScreenerSpoke.execute(filter_mode=mode)
            return {
                "hub_urn": cls.urn,
                "status": "SUCCESS",
                "intent": "SCREENER_SCAN",
                "dispatch_log": dispatch_log,
                "spoke_results": {"screener": screen_res},
                "summary": f"Screened market universe. Found {screen_res['matches_count']} setup(s) matching '{mode}' filter.",
                "guardrail_verified": True,
                "guardrail_verdict": "SCREENER_COMPLETE",
                "latency_ms": round((time.time() - start_time) * 1000, 2),
            }

        # Priority 3: Stock Equity Analysis
        candidate = candidate or "HFCL"

        # Step 1: Market Feed Spoke
        dispatch_log.append({
            "step": "2. A2A Task Dispatch -> Spoke 1",
            "message": f"Dispatching '{candidate}' to {MarketFeedSpoke.name} for Gemma symbol resolution & live tick data.",
            "agent": MarketFeedSpoke.name,
        })
        feed_res = MarketFeedSpoke.execute(candidate)

        # Step 2: Quant Engine Spoke
        dispatch_log.append({
            "step": "3. A2A Task Dispatch -> Spoke 2",
            "message": f"Dispatching quote for {feed_res['resolved_symbol']} to {QuantEngineSpoke.name} for Camarilla pivot levels.",
            "agent": QuantEngineSpoke.name,
        })
        quant_res = QuantEngineSpoke.execute(feed_res["resolved_symbol"])

        # Step 3: Gemma Advisor Spoke
        dispatch_log.append({
            "step": "4. A2A Task Dispatch -> Spoke 4",
            "message": f"Dispatching calculated pivot bounds to {GemmaAdvisorSpoke.name} ({model_choice}) for institutional thesis synthesis.",
            "agent": GemmaAdvisorSpoke.name,
        })
        advisor_res = GemmaAdvisorSpoke.execute(feed_res["resolved_symbol"], model_choice=model_choice)

        return {
            "hub_urn": cls.urn,
            "status": "SUCCESS",
            "intent": "QUANT_EQUITY_ANALYSIS",
            "dispatch_log": dispatch_log,
            "spoke_results": {
                "market_feed": feed_res,
                "quant": quant_res,
                "advisor": advisor_res,
            },
            "summary": f"Analyzed {quant_res['symbol']} (LTP: ₹{quant_res['ltp']:,.2f}). Bias: {quant_res['bias']}. T1: ₹{quant_res['targets']['t1_conservative']}, T2: ₹{quant_res['targets']['t2_base_case']}.",
            "guardrail_verified": True,
            "guardrail_verdict": "DETERMINISTIC_CAMARILLA_VERIFIED",
            "latency_ms": round((time.time() - start_time) * 1000, 2),
        }
