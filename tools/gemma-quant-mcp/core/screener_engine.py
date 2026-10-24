"""
Stock Universe & Screener Engine for Gemma Quant MCP.
Extracted from DalalDesk Equity Screener.
Provides benchmark equity universe and multi-metric filtering.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class ScreenerStock(BaseModel):
    symbol: str
    name: str
    sector: str
    ltp: float
    pe: float
    pb: float
    roe: float
    roce: float
    debt_to_equity: float
    change_pct: float
    high52: float
    low52: float
    volume: int


BENCHMARK_UNIVERSE: List[Dict[str, Any]] = [
    {
        "symbol": "RELIANCE",
        "name": "Reliance Industries Ltd",
        "sector": "Energy & Conglomerate",
        "ltp": 2985.40,
        "pe": 26.4,
        "pb": 2.1,
        "roe": 10.5,
        "roce": 11.2,
        "debt_to_equity": 0.42,
        "change_pct": 1.25,
        "high52": 3024.90,
        "low52": 2220.30,
        "volume": 6842000,
    },
    {
        "symbol": "TCS",
        "name": "Tata Consultancy Services Ltd",
        "sector": "Information Technology",
        "ltp": 4120.00,
        "pe": 29.8,
        "pb": 13.4,
        "roe": 48.2,
        "roce": 61.5,
        "debt_to_equity": 0.05,
        "change_pct": -0.45,
        "high52": 4585.90,
        "low52": 3313.00,
        "volume": 2150000,
    },
    {
        "symbol": "HDFCBANK",
        "name": "HDFC Bank Ltd",
        "sector": "Banking & Financial Services",
        "ltp": 1680.50,
        "pe": 18.5,
        "pb": 2.6,
        "roe": 16.8,
        "roce": 17.5,
        "debt_to_equity": 0.85,
        "change_pct": 1.80,
        "high52": 1794.00,
        "low52": 1363.55,
        "volume": 14200000,
    },
    {
        "symbol": "INFY",
        "name": "Infosys Ltd",
        "sector": "Information Technology",
        "ltp": 1845.20,
        "pe": 27.1,
        "pb": 8.5,
        "roe": 31.8,
        "roce": 40.2,
        "debt_to_equity": 0.08,
        "change_pct": 0.90,
        "high52": 1991.45,
        "low52": 1358.35,
        "volume": 4920000,
    },
    {
        "symbol": "ICICIBANK",
        "name": "ICICI Bank Ltd",
        "sector": "Banking & Financial Services",
        "ltp": 1260.00,
        "pe": 17.2,
        "pb": 2.9,
        "roe": 18.4,
        "roce": 19.1,
        "debt_to_equity": 0.78,
        "change_pct": 2.10,
        "high52": 1300.90,
        "low52": 913.80,
        "volume": 18900000,
    },
    {
        "symbol": "ITC",
        "name": "ITC Ltd",
        "sector": "FMCG",
        "ltp": 485.60,
        "pe": 28.2,
        "pb": 8.1,
        "roe": 29.4,
        "roce": 39.0,
        "debt_to_equity": 0.01,
        "change_pct": 0.35,
        "high52": 510.65,
        "low52": 399.30,
        "volume": 9400000,
    },
    {
        "symbol": "LT",
        "name": "Larsen & Toubro Ltd",
        "sector": "Infrastructure & Capital Goods",
        "ltp": 3620.00,
        "pe": 34.5,
        "pb": 5.2,
        "roe": 15.6,
        "roce": 17.8,
        "debt_to_equity": 0.65,
        "change_pct": 1.40,
        "high52": 3948.60,
        "low52": 2872.25,
        "volume": 3100000,
    },
    {
        "symbol": "BHARTIARTL",
        "name": "Bharti Airtel Ltd",
        "sector": "Telecommunications",
        "ltp": 1690.00,
        "pe": 55.0,
        "pb": 9.8,
        "roe": 18.2,
        "roce": 15.4,
        "debt_to_equity": 1.10,
        "change_pct": 2.45,
        "high52": 1715.00,
        "low52": 890.00,
        "volume": 5800000,
    },
]


def screen_stocks(
    max_pe: Optional[float] = None,
    min_roe: Optional[float] = None,
    max_debt_to_equity: Optional[float] = None,
    min_change_pct: Optional[float] = None,
    sector: Optional[str] = None,
    preset: Optional[str] = None,
) -> List[ScreenerStock]:
    """
    Screens equity universe using fundamental and technical filters.
    """
    if preset == "undervalued_quality":
        max_pe = 25.0
        min_roe = 15.0
        max_debt_to_equity = 0.8
    elif preset == "momentum_breakout":
        min_change_pct = 1.0
    elif preset == "defensive_cashflow":
        max_debt_to_equity = 0.1
        min_roe = 20.0

    results: List[ScreenerStock] = []
    for item in BENCHMARK_UNIVERSE:
        stock = ScreenerStock(**item)
        if max_pe is not None and stock.pe > max_pe:
            continue
        if min_roe is not None and stock.roe < min_roe:
            continue
        if max_debt_to_equity is not None and stock.debt_to_equity > max_debt_to_equity:
            continue
        if min_change_pct is not None and stock.change_pct < min_change_pct:
            continue
        if sector and sector.lower() not in stock.sector.lower():
            continue
        results.append(stock)

    return results
