"""
Unit tests for Gemma Quant MCP & Financial Invariant Engine.
Verifies mathematical precision of pivots, invariant guardrails, and screener logic.
"""

import pytest
from core.models import StockQuote, LedgerEntry, AllocationItem
from core.quant_engine import calculate_quant_targets
from core.invariant_guardrails import audit_invariants
from core.screener_engine import screen_stocks
from core.gemma_advisor import generate_gemma_thesis


def test_classic_and_camarilla_pivots():
    quote = StockQuote(
        symbol="NIFTY_STOCK",
        ltp=1000.0,
        high=1020.0,
        low=980.0,
        close=1000.0,
    )
    targets = calculate_quant_targets(quote)

    # Range = 40.0
    # Classic P = (1020 + 980 + 1000) / 3 = 1000.0
    assert targets.classic_pivots.pivot == 1000.0
    assert targets.classic_pivots.r1 == round(2 * 1000.0 - 980.0, 2)  # 1020.0
    assert targets.classic_pivots.s1 == round(2 * 1000.0 - 1020.0, 2)  # 980.0

    # Camarilla H4 = Close + Range * 1.1 / 2 = 1000 + 40 * 0.55 = 1022.0
    assert targets.camarilla.h4_breakout == 1022.0
    # Camarilla L4 = Close - Range * 1.1 / 2 = 1000 - 22 = 978.0
    assert targets.camarilla.l4_breakdown == 978.0


def test_quant_targets_and_bias():
    quote = StockQuote(
        symbol="BULLISH_TEST",
        ltp=1050.0,
        high=1030.0,
        low=980.0,
        close=990.0,
        change_pct=6.0,
    )
    targets = calculate_quant_targets(quote)
    assert targets.bias == "STRONG BULLISH"
    assert targets.composite_score >= 80
    assert targets.targets.t1_conservative > targets.ltp or targets.targets.t1_conservative > 0
    assert targets.stop_loss.recommended < targets.ltp


def test_invariant_zero_sum_balanced():
    entries = [
        LedgerEntry(entity="Alice", amount=-1400.00),
        LedgerEntry(entity="Bob", amount=700.00),
        LedgerEntry(entity="Charlie", amount=700.00),
    ]
    report = audit_invariants(entries=entries)
    assert report.status == "PASSED"
    assert report.is_zero_sum_balanced is True
    assert report.total_delta == 0.0
    assert len(report.anomalies) == 0


def test_invariant_zero_sum_unbalanced_breach():
    entries = [
        LedgerEntry(entity="Alice", amount=-1400.00),
        LedgerEntry(entity="Bob", amount=600.00),
        LedgerEntry(entity="Charlie", amount=700.00),
    ]
    report = audit_invariants(entries=entries)
    assert report.status == "FAILED"
    assert report.is_zero_sum_balanced is False
    assert report.total_delta == -100.00
    assert any("Zero-Sum Invariant Violation" in a for a in report.anomalies)


def test_allocation_and_concentration_guardrails():
    # HIGH_RISK_STOCK has 70% weight (breaches 25% max limit)
    # SAFE_BOND has 20% and CASH has 10% (both within 25% limit)
    allocations = [
        AllocationItem(asset="HIGH_RISK_STOCK", weight_pct=70.0, value=70000.0),
        AllocationItem(asset="SAFE_BOND", weight_pct=20.0, value=20000.0),
        AllocationItem(asset="CASH", weight_pct=10.0, value=10000.0),
    ]
    report = audit_invariants(allocations=allocations, max_single_weight_pct=25.0)
    assert report.is_allocation_100_pct is True
    assert len(report.concentration_alerts) == 1
    assert "HIGH_RISK_STOCK" in report.concentration_alerts[0]


def test_screener_engine():
    results = screen_stocks(preset="undervalued_quality")
    assert len(results) >= 1
    for stock in results:
        assert stock.pe <= 25.0
        assert stock.roe >= 15.0
        assert stock.debt_to_equity <= 0.8


def test_gemma_thesis_generation():
    quote = StockQuote(symbol="RELIANCE", ltp=2985.4, high=3010.0, low=2960.0, close=2975.0)
    targets = calculate_quant_targets(quote)
    thesis = generate_gemma_thesis(targets)
    assert thesis.symbol == "RELIANCE"
    assert len(thesis.strategic_rationale) > 0
    assert len(thesis.risk_factors) > 0
    assert thesis.suggested_action != ""
