"""
Gemma & Google AI Thesis Generator.
Generates institutional equity research theses, structural risk analyses, and actionable strategies
using Google GenAI (Gemma / Gemini 1.5 Flash) with resilient offline deterministic fallback.
"""

from __future__ import annotations
import os
import json
from typing import Optional
from core.models import QuantTargets, GemmaThesis


def generate_gemma_thesis(targets: QuantTargets, api_key: Optional[str] = None) -> GemmaThesis:
    """
    Synthesizes quantitative targets into an institutional-grade investment thesis.
    Uses Google GenAI if API key is present, otherwise executes offline deterministic synthesis.
    """
    key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    if key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-1.5-flash")

            prompt = f"""
You are an expert equity research quantitative analyst.
Analyze the following quantitative metrics for {targets.symbol}:
- LTP: {targets.ltp}
- Algorithmic Bias: {targets.bias}
- Composite Conviction Score: {targets.composite_score}/100
- ATR Volatility: {targets.atr_volatility_pct}%
- Conservative Target (T1): {targets.targets.t1_conservative}
- Base Target (T2): {targets.targets.t2_base_case}
- Extended Target (T3): {targets.targets.t3_extended}
- Recommended Stop Loss: {targets.stop_loss.recommended}
- Risk/Reward: {targets.risk_reward_ratio}
- Camarilla Bounds: H4={targets.camarilla.h4_breakout}, L4={targets.camarilla.l4_breakdown}

Return a valid JSON object matching this schema:
{{
  "summary": "1-2 sentence executive market stance",
  "strategic_rationale": ["bullet 1", "bullet 2", "bullet 3"],
  "risk_factors": ["risk 1", "risk 2"],
  "suggested_action": "Clear actionable order directive"
}}
Do NOT output markdown code fences, only raw JSON.
"""
            resp = model.generate_content(prompt)
            clean_text = resp.text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]

            data = json.loads(clean_text.strip())
            return GemmaThesis(
                symbol=targets.symbol,
                bias=targets.bias,
                summary=data.get("summary", f"{targets.symbol} demonstrates {targets.bias} momentum."),
                strategic_rationale=data.get("strategic_rationale", []),
                risk_factors=data.get("risk_factors", []),
                suggested_action=data.get("suggested_action", "Maintain position discipline."),
                model="Google Gemini 1.5 Flash / Gemma",
            )
        except Exception:
            # Fall back to offline deterministic synthesis
            pass

    # Offline Deterministic Synthesis Engine (Zero tokens, 100% resilient)
    if targets.bias in ("STRONG BULLISH", "BULLISH ACCUMULATION"):
        summary = (
            f"{targets.symbol} exhibits strong positive momentum with a composite conviction of "
            f"{targets.composite_score}/100. Price action is holding above key Camarilla support."
        )
        rationales = [
            f"Trading above pivot anchor {targets.classic_pivots.pivot} with favorable ATR volatility of {targets.atr_volatility_pct}%.",
            f"Camarilla H4 breakout level ({targets.camarilla.h4_breakout}) presents an asymmetric expansion corridor towards T2 ({targets.targets.t2_base_case}).",
            f"Asymmetric risk-to-reward ratio of {targets.risk_reward_ratio} provides structural downside protection at {targets.stop_loss.recommended}.",
        ]
        risks = [
            f"Intraday rejection below Camarilla L3 ({targets.camarilla.l3_support}) invalidates accumulation structure.",
            "Broader benchmark sector rotation could compress short-term liquidity.",
        ]
        action = f"ACCUMULATE with T1: {targets.targets.t1_conservative}, T2: {targets.targets.t2_base_case}, and SL: {targets.stop_loss.recommended}."
    elif targets.bias == "BEARISH DISTRIBUTION":
        summary = (
            f"{targets.symbol} displays distribution pressure with conviction score of {targets.composite_score}/100, "
            f"indicating breach below primary Camarilla support bounds."
        )
        rationales = [
            f"Price trading below structural pivot ({targets.classic_pivots.pivot}) indicates institutional selling.",
            f"Camarilla breakdown below L4 ({targets.camarilla.l4_breakdown}) opens downside risk towards S2/S3 levels.",
        ]
        risks = [
            f"Sharp short-covering rally above Camarilla H3 ({targets.camarilla.h3_resistance}) could trigger whipsaw.",
        ]
        action = f"DEFENSIVE HEDGE / REDUCE EXPOSURE. Re-evaluate if price reclaims {targets.classic_pivots.pivot}."
    else:
        summary = (
            f"{targets.symbol} is consolidating within a neutral volatility band with conviction score {targets.composite_score}/100."
        )
        rationales = [
            f"Oscillating between Camarilla L3 ({targets.camarilla.l3_support}) and H3 ({targets.camarilla.h3_resistance}).",
            "Compression in ATR volatility indicates an impending directional breakout.",
        ]
        risks = [
            "Range-bound chop may decay option premiums or create false breakout traps.",
        ]
        action = f"WAIT FOR BREAKOUT beyond H4 ({targets.camarilla.h4_breakout}) or L4 ({targets.camarilla.l4_breakdown})."

    return GemmaThesis(
        symbol=targets.symbol,
        bias=targets.bias,
        summary=summary,
        strategic_rationale=rationales,
        risk_factors=risks,
        suggested_action=action,
        model="Deterministic Gemma-Heuristic Engine",
    )
