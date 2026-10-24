"""
Data models for Gemma Quant MCP.
Defines schemas for Stock Quotes, Quantitative Targets, Pivot Matrices,
Financial Invariant Audits, and Gemma Theses.
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class StockQuote(BaseModel):
    symbol: str
    ltp: float = Field(..., gt=0.0, description="Last Traded Price")
    high: float = Field(..., gt=0.0, description="Day High")
    low: float = Field(..., gt=0.0, description="Day Low")
    close: float = Field(..., gt=0.0, description="Previous or Session Close")
    open: Optional[float] = None
    volume: Optional[int] = 0
    high52: Optional[float] = None
    low52: Optional[float] = None
    change_pct: Optional[float] = 0.0


class ClassicPivots(BaseModel):
    pivot: float
    r1: float
    r2: float
    r3: float
    s1: float
    s2: float
    s3: float


class CamarillaPivots(BaseModel):
    h4_breakout: float
    h3_resistance: float
    l3_support: float
    l4_breakdown: float


class FibonacciLevels(BaseModel):
    ext1618: float
    ext1272: float
    ret50: float
    ret618: float


class TargetLevels(BaseModel):
    t1_conservative: float
    t2_base_case: float
    t3_extended: float


class StopLossLevels(BaseModel):
    recommended: float
    tight: float
    structural: float


class QuantTargets(BaseModel):
    symbol: str
    ltp: float
    bias: Literal[
        "STRONG BULLISH",
        "BULLISH ACCUMULATION",
        "NEUTRAL RANGE",
        "BEARISH DISTRIBUTION",
        "HIGH VOLATILITY BREAKOUT"
    ]
    composite_score: int = Field(..., ge=0, le=100)
    confidence_pct: float = Field(..., ge=0.0, le=100.0)
    targets: TargetLevels
    stop_loss: StopLossLevels
    risk_reward_ratio: str
    classic_pivots: ClassicPivots
    camarilla: CamarillaPivots
    fibonacci: FibonacciLevels
    atr_volatility_pct: float


class LedgerEntry(BaseModel):
    entity: str
    amount: float  # Positive = credit/received, negative = debit/paid


class AllocationItem(BaseModel):
    asset: str
    weight_pct: float
    value: float


class InvariantAuditReport(BaseModel):
    status: Literal["PASSED", "FAILED"]
    total_delta: float
    is_zero_sum_balanced: bool
    weights_sum_pct: float
    is_allocation_100_pct: bool
    drift_detected: bool
    concentration_alerts: List[str] = Field(default_factory=list)
    anomalies: List[str] = Field(default_factory=list)
    verdict: str


class GemmaThesis(BaseModel):
    symbol: str
    bias: str
    summary: str
    strategic_rationale: List[str]
    risk_factors: List[str]
    suggested_action: str
    model: str = "Gemma-2-9B / Gemini-1.5-Flash"
