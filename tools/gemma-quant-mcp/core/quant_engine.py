"""
Quantitative Equity Engine for Gemma Quant MCP.
Extracted from DalalDesk Certified Algorithms.
Implements Classic Pivots, Camarilla Breakout/Reversal Bounds, ATR Volatility Projections,
Fibonacci Extensions, and Weighted Algorithmic Conviction Scoring.
"""

from __future__ import annotations
import math
from typing import Dict, Any
from core.models import (
    StockQuote,
    QuantTargets,
    ClassicPivots,
    CamarillaPivots,
    FibonacciLevels,
    TargetLevels,
    StopLossLevels,
)


def calculate_quant_targets(quote: StockQuote) -> QuantTargets:
    """
    Computes deterministic mathematical pivot levels, volatility bounds,
    algorithmic targets, and conviction score.
    """
    h = quote.high
    l = quote.low
    c = quote.close
    ltp = quote.ltp
    rng = max(h - l, 0.01)

    # 1. Classic Pivots
    p = (h + l + c) / 3.0
    r1 = (2.0 * p) - l
    s1 = (2.0 * p) - h
    r2 = p + rng
    s2 = p - rng
    r3 = h + 2.0 * (p - l)
    s3 = l - 2.0 * (h - p)

    classic = ClassicPivots(
        pivot=round(p, 2),
        r1=round(r1, 2),
        r2=round(r2, 2),
        r3=round(r3, 2),
        s1=round(s1, 2),
        s2=round(s2, 2),
        s3=round(s3, 2),
    )

    # 2. Camarilla Equations
    h4 = c + (rng * 1.1 / 2.0)
    h3 = c + (rng * 1.1 / 4.0)
    l3 = c - (rng * 1.1 / 4.0)
    l4 = c - (rng * 1.1 / 2.0)

    camarilla = CamarillaPivots(
        h4_breakout=round(h4, 2),
        h3_resistance=round(h3, 2),
        l3_support=round(l3, 2),
        l4_breakdown=round(l4, 2),
    )

    # 3. Fibonacci Levels
    fib = FibonacciLevels(
        ext1618=round(c + rng * 1.618, 2),
        ext1272=round(c + rng * 1.272, 2),
        ret50=round(c - rng * 0.500, 2),
        ret618=round(c - rng * 0.618, 2),
    )

    # 4. ATR / True Range Volatility
    true_range = max(h - l, abs(h - c), abs(l - c))
    atr_pct = round((true_range / c) * 100.0, 2)

    # 5. Composite Conviction Score (0 to 100)
    # Factor A: Position relative to pivot (0 to 30)
    score_pivot = 15
    if ltp >= r2:
        score_pivot = 30
    elif ltp >= r1:
        score_pivot = 25
    elif ltp >= p:
        score_pivot = 20
    elif ltp <= s2:
        score_pivot = 5
    elif ltp <= s1:
        score_pivot = 10

    # Factor B: Day's Change % (0 to 30)
    chg = quote.change_pct if quote.change_pct is not None else ((ltp - c) / c) * 100.0
    if chg > 3.0:
        score_chg = 30
    elif chg > 1.5:
        score_chg = 25
    elif chg > 0.0:
        score_chg = 20
    elif chg > -1.5:
        score_chg = 12
    else:
        score_chg = 5

    # Factor C: 52-week position (0 to 25)
    score_52w = 12
    if quote.high52 and quote.low52 and quote.high52 > quote.low52:
        pct_52w = (ltp - quote.low52) / (quote.high52 - quote.low52)
        score_52w = int(pct_52w * 25.0)

    # Factor D: Camarilla Breakout Status (0 to 15)
    score_cam = 7
    if ltp > h4:
        score_cam = 15  # Active bullish breakout
    elif ltp > h3:
        score_cam = 12
    elif ltp < l4:
        score_cam = 2   # Breakdown
    elif ltp < l3:
        score_cam = 5

    composite_score = min(100, max(0, score_pivot + score_chg + score_52w + score_cam))
    confidence_pct = round(min(98.5, max(52.0, 50.0 + (composite_score / 2.0))), 1)

    # Determine Bias
    if ltp > h4 or composite_score >= 80:
        bias = "STRONG BULLISH"
    elif ltp >= p and composite_score >= 60:
        bias = "BULLISH ACCUMULATION"
    elif ltp < l4 or composite_score <= 30:
        bias = "BEARISH DISTRIBUTION"
    elif atr_pct >= 4.0:
        bias = "HIGH VOLATILITY BREAKOUT"
    else:
        bias = "NEUTRAL RANGE"

    # Targets & Stop Loss
    if bias in ("STRONG BULLISH", "BULLISH ACCUMULATION", "HIGH VOLATILITY BREAKOUT"):
        t1 = round(max(ltp * 1.008, h3), 2)
        t2 = round(max(t1 * 1.012, h4, r2), 2)
        t3 = round(max(t2 * 1.015, fib.ext1618, r3), 2)
        sl_rec = round(min(ltp * 0.988, l3, s1), 2)
        sl_tight = round(min(ltp * 0.993, p), 2)
        sl_struct = round(min(ltp * 0.980, l4, s2), 2)
    else:
        t1 = round(min(ltp * 0.992, l3), 2)
        t2 = round(min(t1 * 0.988, l4, s2), 2)
        t3 = round(min(t2 * 0.985, fib.ret618, s3), 2)
        sl_rec = round(max(ltp * 1.012, h3, r1), 2)
        sl_tight = round(max(ltp * 1.007, p), 2)
        sl_struct = round(max(ltp * 1.020, h4, r2), 2)

    risk = abs(ltp - sl_rec)
    reward = abs(t2 - ltp)
    rr_ratio = f"1:{round(reward / risk, 2)}" if risk > 0 else "1:2.00"

    return QuantTargets(
        symbol=quote.symbol.upper(),
        ltp=round(ltp, 2),
        bias=bias,
        composite_score=composite_score,
        confidence_pct=confidence_pct,
        targets=TargetLevels(
            t1_conservative=t1,
            t2_base_case=t2,
            t3_extended=t3,
        ),
        stop_loss=StopLossLevels(
            recommended=sl_rec,
            tight=sl_tight,
            structural=sl_struct,
        ),
        risk_reward_ratio=rr_ratio,
        classic_pivots=classic,
        camarilla=camarilla,
        fibonacci=fib,
        atr_volatility_pct=atr_pct,
    )
