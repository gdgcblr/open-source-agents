"""
Deterministic Portfolio & Rebalancing Financial Tools
=====================================================
All calculations (market values, allocation percentages, drift deltas, share
counts, and order amounts) are strictly computed deterministically via Python.
The LLM does NOT estimate or approximate financial math.
"""

from __future__ import annotations
import os
import math
import warnings
from typing import Any, Dict, List, Optional
import pandas as pd

# Suppress harmless OpenSSL/urllib3 warnings on certain Python runtimes
warnings.filterwarnings("ignore")

try:
    import yfinance as yf
except ImportError:
    yf = None

# -----------------------------------------------------------------------------
# Curated Fallback / Offline Mock Database
# Used when offline, during network timeouts, or when USE_MOCK_DATA=1
# -----------------------------------------------------------------------------
MOCK_PRICES: Dict[str, Dict[str, Any]] = {
    "RELIANCE.NS": {
        "ticker": "RELIANCE.NS",
        "name": "Reliance Industries Limited",
        "current_price": 1285.50,
        "currency": "INR",
        "change_52w_pct": 14.85,
        "asset_class": "Indian Equity",
        "sector": "Energy & Conglomerate"
    },
    "TCS.NS": {
        "ticker": "TCS.NS",
        "name": "Tata Consultancy Services Ltd",
        "current_price": 3520.00,
        "currency": "INR",
        "change_52w_pct": -6.40,
        "asset_class": "Indian Equity",
        "sector": "Information Technology"
    },
    "HDFCBANK.NS": {
        "ticker": "HDFCBANK.NS",
        "name": "HDFC Bank Limited",
        "current_price": 1680.00,
        "currency": "INR",
        "change_52w_pct": 12.15,
        "asset_class": "Indian Equity",
        "sector": "Financial Services"
    },
    "NIFTYBEES.NS": {
        "ticker": "NIFTYBEES.NS",
        "name": "Nippon India ETF Nifty 50 BeES",
        "current_price": 265.40,
        "currency": "INR",
        "change_52w_pct": 18.20,
        "asset_class": "Indian Equity",
        "sector": "Large Cap Index"
    },
    "MON100.NS": {
        "ticker": "MON100.NS",
        "name": "Motilal Oswal Nasdaq 100 ETF",
        "current_price": 172.80,
        "currency": "INR",
        "change_52w_pct": 28.50,
        "asset_class": "International Equity",
        "sector": "US Technology / Global"
    },
    "GOLDBEES.NS": {
        "ticker": "GOLDBEES.NS",
        "name": "Nippon India ETF Gold BeES",
        "current_price": 68.20,
        "currency": "INR",
        "change_52w_pct": 22.40,
        "asset_class": "Gold / Commodities",
        "sector": "Precious Metals"
    },
    "LIQUIDBEES.NS": {
        "ticker": "LIQUIDBEES.NS",
        "name": "Nippon India ETF Liquid BeES",
        "current_price": 1000.00,
        "currency": "INR",
        "change_52w_pct": 6.85,
        "asset_class": "Fixed Income / Debt",
        "sector": "Money Market / Liquid"
    },
    "GOI_BONDS": {
        "ticker": "GOI_BONDS",
        "name": "Government of India 7.18% GS 2033 Bond",
        "current_price": 1025.00,
        "currency": "INR",
        "change_52w_pct": 4.50,
        "asset_class": "Fixed Income / Debt",
        "sector": "Sovereign Debt"
    },
    "INFY.NS": {
        "ticker": "INFY.NS",
        "name": "Infosys Limited",
        "current_price": 1820.00,
        "currency": "INR",
        "change_52w_pct": 21.30,
        "asset_class": "Indian Equity",
        "sector": "Information Technology"
    },
    "ICICIBANK.NS": {
        "ticker": "ICICIBANK.NS",
        "name": "ICICI Bank Limited",
        "current_price": 1260.00,
        "currency": "INR",
        "change_52w_pct": 19.80,
        "asset_class": "Indian Equity",
        "sector": "Financial Services"
    },
    "ITC.NS": {
        "ticker": "ITC.NS",
        "name": "ITC Limited",
        "current_price": 475.00,
        "currency": "INR",
        "change_52w_pct": 11.20,
        "asset_class": "Indian Equity",
        "sector": "Consumer Goods"
    },
    "SBIN.NS": {
        "ticker": "SBIN.NS",
        "name": "State Bank of India",
        "current_price": 790.00,
        "currency": "INR",
        "change_52w_pct": 34.50,
        "asset_class": "Indian Equity",
        "sector": "Banking & Financials"
    },
    "TATAMOTORS.NS": {
        "ticker": "TATAMOTORS.NS",
        "name": "Tata Motors Limited",
        "current_price": 880.00,
        "currency": "INR",
        "change_52w_pct": 32.10,
        "asset_class": "Indian Equity",
        "sector": "Automotive"
    },
    "SILVERBEES.NS": {
        "ticker": "SILVERBEES.NS",
        "name": "Nippon India ETF Silver BeES",
        "current_price": 92.50,
        "currency": "INR",
        "change_52w_pct": 31.40,
        "asset_class": "Gold / Commodities",
        "sector": "Precious Metals"
    },
    "INR_CASH": {
        "ticker": "INR_CASH",
        "name": "High Yield Bank Savings / Emergency Cash",
        "current_price": 1.00,
        "currency": "INR",
        "change_52w_pct": 0.00,
        "asset_class": "Cash & Equivalents",
        "sector": "Liquid Savings"
    }
}

# Alias dictionary for common Indian stock/ETF names
TICKER_ALIASES: Dict[str, str] = {
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "INFY": "INFY.NS",
    "INFOSYS": "INFY.NS",
    "HDFC": "HDFCBANK.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "ICICI": "ICICIBANK.NS",
    "ICICIBANK": "ICICIBANK.NS",
    "SBIN": "SBIN.NS",
    "SBI": "SBIN.NS",
    "ITC": "ITC.NS",
    "TATAMOTORS": "TATAMOTORS.NS",
    "TATA MOTORS": "TATAMOTORS.NS",
    "AIRTEL": "BHARTIARTL.NS",
    "BHARTIARTL": "BHARTIARTL.NS",
    "WIPRO": "WIPRO.NS",
    "NIFTYBEES": "NIFTYBEES.NS",
    "NIFTY BEES": "NIFTYBEES.NS",
    "GOLDBEES": "GOLDBEES.NS",
    "GOLD BEES": "GOLDBEES.NS",
    "SILVERBEES": "SILVERBEES.NS",
    "LIQUIDBEES": "LIQUIDBEES.NS",
    "MON100": "MON100.NS",
    "NASDAQ100": "MON100.NS",
    "CASH": "INR_CASH",
    "INR": "INR_CASH",
    "SAVINGS": "INR_CASH",
    "FD": "INR_CASH",
    "BANK": "INR_CASH"
}


def normalize_indian_ticker(symbol: str) -> str:
    """
    Normalizes user-input stock/ETF symbol to canonical ticker (e.g., RELIANCE -> RELIANCE.NS).
    Preserves existing suffixes (.NS, .BO) and US tickers.
    """
    clean = symbol.strip().upper()
    if clean in TICKER_ALIASES:
        return TICKER_ALIASES[clean]
    if clean.endswith(".NS") or clean.endswith(".BO"):
        return clean
    if clean in ("INR_CASH", "GOI_BONDS", "VOO", "QQQ", "SPY", "AAPL", "MSFT", "GOOGL"):
        return clean
    # Default to National Stock Exchange (.NS)
    return f"{clean}.NS"


def infer_asset_class(ticker: str, name: str = "") -> str:
    """Infers the asset class from ticker symbol and name."""
    t = ticker.upper()
    n = name.upper()
    if "CASH" in t or "SAVINGS" in t or "FD" in t:
        return "Cash & Equivalents"
    if "GOLD" in t or "SILVER" in t or "COMMODITY" in n or "GOLD" in n:
        return "Gold / Commodities"
    if "LIQUID" in t or "BOND" in t or "DEBT" in t or "GILT" in t or "GOI" in t or "TREASURY" in n:
        return "Fixed Income / Debt"
    if "MON100" in t or "NASDAQ" in t or "VOO" in t or "QQQ" in t or "SPY" in t or "GLOBAL" in n:
        return "International Equity"
    return "Indian Equity"


def parse_holdings_shorthand(holdings_str: str) -> List[Dict[str, Any]]:
    """
    Deterministically parses comma/semicolon-separated user holdings string.
    Example inputs:
      'RELIANCE:50, TCS:30, GOLDBEES:200, CASH:50000'
      'RELIANCE.NS=100; INFY=50; INR_CASH=25000'
    """
    holdings: List[Dict[str, Any]] = []
    import re
    # Split by comma or semicolon
    tokens = re.split(r"[,;]+", holdings_str)
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        # Support formats: TICKER:SHARES, TICKER=SHARES, TICKER SHARES
        match = re.match(r"^([A-Za-z0-9_.\s]+?)[:=\s]+([0-9,.]+)\s*(?:shares|units|inr|rs)?$", token, re.IGNORECASE)
        if match:
            sym_raw = match.group(1).strip()
            qty_raw = match.group(2).replace(",", "").strip()
            try:
                qty = float(qty_raw)
            except ValueError:
                continue

            ticker = normalize_indian_ticker(sym_raw)
            asset_class = infer_asset_class(ticker)
            name = MOCK_PRICES.get(ticker, {}).get("name", sym_raw.title())

            holdings.append({
                "ticker": ticker,
                "name": name,
                "shares": qty,
                "asset_class": asset_class,
                "sector": MOCK_PRICES.get(ticker, {}).get("sector", "General")
            })

    return holdings


def parse_indian_currency_expression(amount_str: str) -> float:
    """
    Parses Indian financial colloquial amounts into float values:
    '50k' -> 50000.0
    '1.5 lakh' / '1.5L' / '1.5 lac' -> 150000.0
    '2 cr' / '2 crore' -> 20000000.0
    'rs.50000' / '₹50,000' -> 50000.0
    """
    if not amount_str:
        return 0.0
    import re
    s = amount_str.lower().replace("rs.", "").replace("rs", "").replace("inr", "").replace("₹", "").replace(",", "").strip()
    m_cr = re.search(r"([\d.]+)\s*(?:cr|crore|crores)\b", s)
    if m_cr:
        return float(m_cr.group(1)) * 10000000.0
    m_l = re.search(r"([\d.]+)\s*(?:lakh|lakhs|lac|lacs|l)\b", s)
    if m_l:
        return float(m_l.group(1)) * 100000.0
    m_k = re.search(r"([\d.]+)\s*k\b", s)
    if m_k:
        return float(m_k.group(1)) * 1000.0
    m_num = re.search(r"([\d.]+)", s)
    if m_num:
        try:
            return float(m_num.group(1))
        except ValueError:
            return 0.0
    return 0.0


def parse_conversational_text(text: str) -> Dict[str, Any]:
    """
    Extracts stocks, cash reserves, fresh cash infusions, and allocation models
    from conversational user messages.
    Example: 'I have 100 stocks of TCS and my available cash is 50k (means rs.50000)'
    """
    import re
    res = {
        "stocks": [],
        "cash": 0.0,
        "cash_infusion": 0.0,
        "target_model": None
    }
    clean_text = text

    # 1. Cash extraction (prefix: 'available cash is 50k', suffix: '50k in cash')
    m1 = re.search(r"(?:available\s+cash|cash\s+balance|savings|bank\s+balance|cash)\s*(?:is|of|amount|=|:)?\s*([₹rs.\d\w\s,]+(?:\([^)]+\))?)", text, re.IGNORECASE)
    m2 = re.search(r"([₹rs.\d]+(?:\.\d+)?\s*(?:cr|crore|lakh|lakhs|lac|lacs|l|k)?)\s+(?:in\s+cash|cash)\b", text, re.IGNORECASE)

    if m1 and any(c.isdigit() for c in m1.group(1)):
        cash_str = m1.group(1)
        clarified = re.search(r"\(means\s+([^)]+)\)", cash_str, re.IGNORECASE)
        val = parse_indian_currency_expression(clarified.group(1) if clarified else cash_str)
        if val > 0:
            res["cash"] = val
            clean_text = clean_text.replace(m1.group(0), " ")
    elif m2:
        val = parse_indian_currency_expression(m2.group(1))
        if val > 0:
            res["cash"] = val
            clean_text = clean_text.replace(m2.group(0), " ")

    # 2. Fresh cash infusion extraction ('infuse 20k', 'add 50k fresh cash')
    infuse_m = re.search(r"(?:infuse\s+cash|cash\s+infusion|infuse|(?:add|invest)\s+(?:fresh\s+|new\s+)?cash)\s*(?:of|is|=|:)?\s*([₹rs.\d\w\s,]+)", clean_text, re.IGNORECASE)
    if not infuse_m and ("share" not in clean_text.lower() and "stock" not in clean_text.lower() and "unit" not in clean_text.lower()):
        infuse_m = re.search(r"(?:add|invest)\s+([₹rs.\d\w\s,]+)", clean_text, re.IGNORECASE)

    if infuse_m:
        val_inf = parse_indian_currency_expression(infuse_m.group(1))
        if val_inf > 0 and val_inf != res["cash"]:
            res["cash_infusion"] = val_inf
            clean_text = clean_text.replace(infuse_m.group(0), " ")

    # 3. Stock extraction (e.g. '100 stocks of TCS', '50 shares of Reliance', '200 GoldBees')
    stock_matches = re.finditer(r"(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:stocks?|shares?|units?)?\s*(?:of\s+)?([A-Za-z0-9_.]+)", clean_text, re.IGNORECASE)
    for m in stock_matches:
        qty_s, sym_s = m.group(1), m.group(2)
        sym_clean = sym_s.strip().upper()
        if sym_clean in ("CASH", "SAVINGS", "RS", "INR", "AND", "MY", "THE", "A", "AN", "OF", "IN", "LAKH", "LAKHS", "CR", "CRORE", "K", "MEANS"):
            continue
        try:
            qty = float(qty_s.replace(",", ""))
            if qty <= 0:
                continue
            ticker = normalize_indian_ticker(sym_clean)
            asset_class = infer_asset_class(ticker)
            name = MOCK_PRICES.get(ticker, {}).get("name", sym_clean.title())
            if not any(s["ticker"] == ticker for s in res["stocks"]):
                res["stocks"].append({
                    "ticker": ticker,
                    "name": name,
                    "shares": qty,
                    "asset_class": asset_class,
                    "sector": MOCK_PRICES.get(ticker, {}).get("sector", "General")
                })
        except ValueError:
            pass

    # 4. Target model detection
    t_lower = text.lower()
    if "aggressive" in t_lower or "high risk" in t_lower:
        res["target_model"] = "Aggressive Growth"
    elif "moderate" in t_lower or "balanced" in t_lower:
        res["target_model"] = "Moderate Balanced"
    elif "conservative" in t_lower or "preserv" in t_lower or "low risk" in t_lower:
        res["target_model"] = "Conservative Preservation"

    return res




def format_inr(amount: float) -> str:
    """Format floating point values into Indian Rupee representation (e.g., ₹1,25,000.00)."""
    if amount is None or math.isnan(amount):
        return "₹0.00"
    is_negative = amount < 0
    abs_amt = abs(amount)
    parts = f"{abs_amt:.2f}".split(".")
    int_part = parts[0]
    dec_part = parts[1]

    if len(int_part) <= 3:
        formatted_int = int_part
    else:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        groups.append(last3)
        formatted_int = ",".join(groups)

    sign = "-" if is_negative else ""
    return f"{sign}₹{formatted_int}.{dec_part}"


def fetch_live_prices(tickers: List[str]) -> Dict[str, Any]:
    """
    Fetch live market prices, 52-week change percentage, and asset metadata for given tickers via yfinance.
    Gracefully falls back to mock/cached data if offline or if tickers are cash/bonds.

    Args:
        tickers: List of ticker symbols (e.g. ['RELIANCE.NS', 'GOLDBEES.NS', 'INR_CASH'])

    Returns:
        dict: Ticker price data, 52-week change %, currency, sector, and asset class.
    """
    force_mock = os.getenv("USE_MOCK_DATA", "0").lower() in ("1", "true", "yes")
    result_prices: Dict[str, Dict[str, Any]] = {}
    fallback_used = False

    for ticker in tickers:
        clean_ticker = normalize_indian_ticker(ticker)

        # Handle Cash / Non-quoted fixed instruments immediately
        if clean_ticker in ("INR_CASH", "CASH", "FD", "SAVINGS"):
            result_prices[clean_ticker] = {
                "ticker": clean_ticker,
                "name": MOCK_PRICES.get(clean_ticker, {}).get("name", "Cash / Bank Deposit"),
                "current_price": 1.00,
                "currency": "INR",
                "change_52w_pct": 0.00,
                "asset_class": "Cash & Equivalents",
                "sector": "Liquid Savings",
                "is_fallback": False
            }
            continue

        if clean_ticker == "GOI_BONDS":
            result_prices[clean_ticker] = {
                "ticker": clean_ticker,
                "name": MOCK_PRICES["GOI_BONDS"]["name"],
                "current_price": MOCK_PRICES["GOI_BONDS"]["current_price"],
                "currency": "INR",
                "change_52w_pct": MOCK_PRICES["GOI_BONDS"]["change_52w_pct"],
                "asset_class": "Fixed Income / Debt",
                "sector": "Sovereign Debt",
                "is_fallback": False
            }
            continue

        if force_mock or yf is None:
            mock_item = MOCK_PRICES.get(clean_ticker)
            if mock_item:
                data = dict(mock_item)
                data["is_fallback"] = True
                result_prices[clean_ticker] = data
            else:
                result_prices[clean_ticker] = {
                    "ticker": clean_ticker,
                    "name": clean_ticker,
                    "current_price": 100.0,
                    "currency": "INR",
                    "change_52w_pct": 0.0,
                    "asset_class": "Indian Equity",
                    "sector": "General",
                    "is_fallback": True
                }
            fallback_used = True
            continue

        # Attempt live lookup via yfinance
        try:
            yt = yf.Ticker(clean_ticker)
            price = None
            change_52w = None
            long_name = clean_ticker
            sector = "Equity"
            asset_class = "Indian Equity"

            # Check fast_info first (fastest)
            if hasattr(yt, "fast_info") and yt.fast_info:
                price = getattr(yt.fast_info, "last_price", None)
                if price is None:
                    price = getattr(yt.fast_info, "previous_close", None)
                year_high = getattr(yt.fast_info, "year_high", None)
                year_low = getattr(yt.fast_info, "year_low", None)
                if year_low and year_low > 0 and price:
                    change_52w = round(((price - year_low) / year_low) * 100, 2)

            # Fallback to info dict if fast_info missing price
            if price is None or price <= 0:
                info = yt.info or {}
                price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
                long_name = info.get("longName") or info.get("shortName") or clean_ticker
                change_52w = info.get("52WeekChange")
                if change_52w is not None:
                    change_52w = round(change_52w * 100, 2)
                sector = info.get("sector") or info.get("category") or sector

            # Infer asset class
            if "GOLD" in clean_ticker or "SILVER" in clean_ticker:
                asset_class = "Gold / Commodities"
            elif "LIQUID" in clean_ticker or "BOND" in clean_ticker or "DEBT" in clean_ticker:
                asset_class = "Fixed Income / Debt"
            elif "MON100" in clean_ticker or "NASDAQ" in clean_ticker or clean_ticker.endswith(".US") or clean_ticker in ("VOO", "QQQ", "SPY"):
                asset_class = "International Equity"
            elif clean_ticker.endswith(".NS") or clean_ticker.endswith(".BO"):
                asset_class = "Indian Equity"

            if price is not None and price > 0:
                result_prices[clean_ticker] = {
                    "ticker": clean_ticker,
                    "name": long_name,
                    "current_price": round(float(price), 2),
                    "currency": "INR",
                    "change_52w_pct": change_52w if change_52w is not None else 0.0,
                    "asset_class": asset_class,
                    "sector": sector,
                    "is_fallback": False
                }
            else:
                raise ValueError(f"Price unavailable for {clean_ticker}")

        except Exception:
            # Gracefully fallback to mock price
            fallback_used = True
            mock_item = MOCK_PRICES.get(clean_ticker)
            if mock_item:
                data = dict(mock_item)
                data["is_fallback"] = True
                result_prices[clean_ticker] = data
            else:
                result_prices[clean_ticker] = {
                    "ticker": clean_ticker,
                    "name": clean_ticker,
                    "current_price": 100.0,
                    "currency": "INR",
                    "change_52w_pct": 0.0,
                    "asset_class": "Indian Equity",
                    "sector": "General",
                    "is_fallback": True
                }

    return {
        "status": "success",
        "data_source": "fallback_mock" if fallback_used else "live_yfinance",
        "prices": result_prices
    }


def calculate_portfolio_drift(
    current_holdings: List[Dict[str, Any]],
    target_allocations: Dict[str, float]
) -> Dict[str, Any]:
    """
    Deterministically calculate the current total portfolio value, current allocation percentages
    vs target allocation percentages, and drift deltas across all asset classes.

    Args:
        current_holdings: List of holdings with 'ticker', 'shares', and optionally 'current_price', 'asset_class'
        target_allocations: Dict of asset class targets, either as decimals (0.40) or percentages (40.0)

    Returns:
        dict: Full deterministic drift analysis including asset class totals, drift percentages,
              and rebalance flags.
    """
    if not current_holdings:
        return {"status": "error", "message": "current_holdings list is empty"}

    # Normalize target allocations to percentages (e.g. 0.40 -> 40.0)
    norm_targets: Dict[str, float] = {}
    sum_targets = sum(target_allocations.values())
    is_decimal = sum_targets <= 1.05

    for k, v in target_allocations.items():
        norm_targets[k] = round(v * 100.0 if is_decimal else float(v), 2)

    # Gather tickers requiring prices
    tickers_to_fetch = [h["ticker"] for h in current_holdings if "current_price" not in h]
    prices_info = fetch_live_prices(tickers_to_fetch)["prices"] if tickers_to_fetch else {}

    # Compute individual holding values
    holdings_enriched = []
    total_portfolio_value = 0.0
    asset_class_values: Dict[str, float] = {k: 0.0 for k in norm_targets.keys()}

    for h in current_holdings:
        ticker = h["ticker"]
        shares = float(h.get("shares", 0))
        price_meta = prices_info.get(ticker, {})

        price = float(h.get("current_price", price_meta.get("current_price", 100.0)))
        asset_class = h.get("asset_class", price_meta.get("asset_class", "Indian Equity"))
        name = h.get("name", price_meta.get("name", ticker))
        sector = h.get("sector", price_meta.get("sector", "N/A"))

        val = round(shares * price, 2)
        total_portfolio_value += val

        if asset_class not in asset_class_values:
            asset_class_values[asset_class] = 0.0
        asset_class_values[asset_class] += val

        holdings_enriched.append({
            "ticker": ticker,
            "name": name,
            "shares": shares,
            "current_price": price,
            "current_value": val,
            "asset_class": asset_class,
            "sector": sector
        })

    total_portfolio_value = round(total_portfolio_value, 2)

    # Compute allocation and drift by asset class
    asset_class_analysis = []
    max_drift = 0.0
    most_overweight = None
    most_underweight = None

    for ac, target_pct in norm_targets.items():
        current_val = round(asset_class_values.get(ac, 0.0), 2)
        current_pct = round((current_val / total_portfolio_value * 100.0) if total_portfolio_value > 0 else 0.0, 2)
        drift_pct = round(current_pct - target_pct, 2)
        target_val = round((target_pct / 100.0) * total_portfolio_value, 2)
        value_drift = round(current_val - target_val, 2)

        # Tolerance threshold: ±1.5%
        if drift_pct > 1.5:
            status = "OVERWEIGHT"
        elif drift_pct < -1.5:
            status = "UNDERWEIGHT"
        else:
            status = "BALANCED"

        if drift_pct > max_drift:
            most_overweight = ac
        if drift_pct < -abs(max_drift):
            most_underweight = ac

        asset_class_analysis.append({
            "asset_class": ac,
            "current_value": current_val,
            "current_value_formatted": format_inr(current_val),
            "current_pct": current_pct,
            "target_pct": target_pct,
            "drift_pct": drift_pct,
            "target_value": target_val,
            "target_value_formatted": format_inr(target_val),
            "value_drift": value_drift,
            "value_drift_formatted": format_inr(value_drift),
            "status": status
        })

    # Holding level percentages
    for h in holdings_enriched:
        h["current_pct"] = round((h["current_value"] / total_portfolio_value * 100.0) if total_portfolio_value > 0 else 0.0, 2)
        h["current_value_formatted"] = format_inr(h["current_value"])
        h["current_price_formatted"] = format_inr(h["current_price"])

    rebalance_needed = any(abs(item["drift_pct"]) > 1.5 for item in asset_class_analysis)

    return {
        "status": "success",
        "total_portfolio_value": total_portfolio_value,
        "total_portfolio_value_formatted": format_inr(total_portfolio_value),
        "rebalance_recommended": rebalance_needed,
        "asset_class_drift": asset_class_analysis,
        "holdings": holdings_enriched,
        "most_overweight_asset_class": most_overweight,
        "most_underweight_asset_class": most_underweight
    }


BENCHMARK_INSTRUMENTS: Dict[str, Dict[str, Any]] = {
    "Gold / Commodities": {
        "ticker": "GOLDBEES.NS",
        "name": "Nippon India ETF Gold BeES",
        "asset_class": "Gold / Commodities",
        "sector": "Precious Metals"
    },
    "Fixed Income / Debt": {
        "ticker": "LIQUIDBEES.NS",
        "name": "Nippon India ETF Liquid BeES",
        "asset_class": "Fixed Income / Debt",
        "sector": "Money Market / Liquid"
    },
    "International Equity": {
        "ticker": "MON100.NS",
        "name": "Motilal Oswal Nasdaq 100 ETF",
        "asset_class": "International Equity",
        "sector": "US Tech / Global"
    },
    "Indian Equity": {
        "ticker": "NIFTYBEES.NS",
        "name": "Nippon India ETF Nifty 50 BeES",
        "asset_class": "Indian Equity",
        "sector": "Large Cap Index"
    }
}


def generate_trade_rationale(
    action: str,
    ticker: str,
    asset_class: str,
    current_pct: float,
    target_pct: float,
    drift_pct: float,
    is_new_position: bool = False
) -> str:
    """
    Explains precisely WHY a stock or asset should be bought, sold, or held.
    """
    if action == "SELL":
        if ticker in ("INR_CASH", "CASH"):
            return (
                f"Cash reserve is overweight ({current_pct:.1f}% vs {target_pct:.1f}% target). "
                f"Deploy idle cash into productive assets to prevent real inflation drag (~5% CPI)."
            )
        if asset_class == "Indian Equity" and current_pct > 30.0:
            return (
                f"De-risk severe single-stock concentration ({current_pct:.1f}% vs {target_pct:.1f}% target). "
                f"Trimming locks in gains and shields portfolio against company-specific shocks."
            )
        return (
            f"Trim position as {asset_class} is overweight by {drift_pct:+.1f}%. "
            f"Rebalance back to the strategic {target_pct:.1f}% target model."
        )

    elif action == "BUY":
        if is_new_position:
            if asset_class == "Gold / Commodities":
                return (
                    f"Establish missing {target_pct:.1f}% Gold allocation. "
                    f"Provides an essential macro hedge against currency depreciation (INR/USD) and market volatility."
                )
            if asset_class == "Fixed Income / Debt":
                return (
                    f"Establish missing {target_pct:.1f}% Fixed Income foundation. "
                    f"Provides capital preservation, steady yield, and stabilizes equity drawdowns."
                )
            if asset_class == "International Equity":
                return (
                    f"Establish missing {target_pct:.1f}% International allocation. "
                    f"Provides geographic diversification and participation in secular US tech growth."
                )
            return (
                f"Establish core {asset_class} allocation to fulfill strategic {target_pct:.1f}% model target."
            )

        if asset_class == "Gold / Commodities":
            return (
                f"Underweight by {drift_pct:+.1f}%. Accumulate Gold ETF to reach target {target_pct:.1f}% "
                f"for geopolitical hedging and inflation resistance."
            )
        if asset_class == "Fixed Income / Debt":
            return (
                f"Underweight by {drift_pct:+.1f}%. Accumulate debt/liquid instruments to reach target {target_pct:.1f}% "
                f"and dampen overall portfolio volatility."
            )
        if asset_class == "International Equity":
            return (
                f"Underweight by {drift_pct:+.1f}%. Add international equity units to reach target {target_pct:.1f}%."
            )
        return (
            f"Underweight by {drift_pct:+.1f}%. Accumulate {ticker} to build up towards target {target_pct:.1f}%."
        )

    return (
        f"Position is well-aligned with target model (drift {drift_pct:+.1f}%). "
        f"Hold to avoid unnecessary brokerage, STT, and capital gains tax."
    )


def calculate_rebalance_orders(
    current_holdings: List[Dict[str, Any]],
    target_allocations: Dict[str, float],
    cash_infusion: float = 0.0
) -> Dict[str, Any]:
    """
    Computes exact, deterministic buy/sell orders (share counts, trade values, and
    post-rebalance allocations) to eliminate portfolio drift against the target model.
    Includes deterministic, institutional-grade rationales explaining WHY to buy/sell each stock.
    Supports optional new cash infusion (inflow rebalancing) to minimize taxable sales.

    Args:
        current_holdings: List of holdings with 'ticker', 'shares', and optionally 'current_price', 'asset_class'
        target_allocations: Target allocation models by asset class (e.g. {'Indian Equity': 0.50, ...})
        cash_infusion: Optional new capital being added (e.g., 50000.0 for ₹50,000 fresh cash)

    Returns:
        dict: Detailed order book with Action (BUY/SELL/HOLD), share counts, trade value,
              rationales explaining WHY, tax awareness metrics, and post-rebalance allocations.
    """
    # First get current drift and valuation
    drift_result = calculate_portfolio_drift(current_holdings, target_allocations)
    if drift_result.get("status") != "success":
        return drift_result

    current_total = drift_result["total_portfolio_value"]
    cash_infusion = max(0.0, float(cash_infusion))
    new_total = round(current_total + cash_infusion, 2)

    # Normalized target allocations
    norm_targets: Dict[str, float] = {}
    sum_targets = sum(target_allocations.values())
    is_decimal = sum_targets <= 1.05
    for k, v in target_allocations.items():
        norm_targets[k] = round(v * 100.0 if is_decimal else float(v), 2)

    # Map current holdings by asset class
    holdings = drift_result["holdings"]
    class_holdings: Dict[str, List[Dict[str, Any]]] = {}
    for h in holdings:
        ac = h["asset_class"]
        class_holdings.setdefault(ac, []).append(h)

    # Compute target values per asset class in the new expanded portfolio
    class_targets: Dict[str, float] = {}
    class_deltas: Dict[str, float] = {}
    for ac, target_pct in norm_targets.items():
        t_val = round((target_pct / 100.0) * new_total, 2)
        c_val = sum(h["current_value"] for h in class_holdings.get(ac, []))
        class_targets[ac] = t_val
        class_deltas[ac] = round(t_val - c_val, 2)

    orders = []
    total_buy_value = 0.0
    total_sell_value = 0.0

    # Distribute class deltas across holdings
    for ac, delta in class_deltas.items():
        sub_holdings = class_holdings.get(ac, [])

        if not sub_holdings:
            # Asset class has target allocation but no existing holding.
            # If positive delta (underweight), introduce the benchmark ETF!
            if delta > 100 and ac in BENCHMARK_INSTRUMENTS:
                bench = BENCHMARK_INSTRUMENTS[ac]
                b_ticker = bench["ticker"]
                b_price_data = fetch_live_prices([b_ticker])["prices"].get(b_ticker, {})
                b_price = float(b_price_data.get("current_price", MOCK_PRICES.get(b_ticker, {}).get("current_price", 100.0)))
                shares_to_buy = int(math.floor(delta / b_price)) if b_price > 0 else 0
                trade_val = round(shares_to_buy * b_price, 2)
                if shares_to_buy > 0:
                    total_buy_value += trade_val
                    post_pct = round((trade_val / new_total * 100.0) if new_total > 0 else 0.0, 2)
                    rat = generate_trade_rationale(
                        action="BUY",
                        ticker=b_ticker,
                        asset_class=ac,
                        current_pct=0.0,
                        target_pct=norm_targets.get(ac, 0.0),
                        drift_pct=-norm_targets.get(ac, 0.0),
                        is_new_position=True
                    )
                    orders.append({
                        "ticker": b_ticker,
                        "name": bench["name"],
                        "asset_class": ac,
                        "action": "BUY",
                        "current_shares": 0,
                        "shares_to_trade": shares_to_buy,
                        "post_trade_shares": shares_to_buy,
                        "unit_price": b_price,
                        "unit_price_formatted": format_inr(b_price),
                        "order_value": trade_val,
                        "order_value_formatted": format_inr(trade_val),
                        "current_value": 0.0,
                        "current_value_formatted": "₹0.00",
                        "post_trade_value": trade_val,
                        "post_trade_value_formatted": format_inr(trade_val),
                        "post_trade_pct": post_pct,
                        "target_pct": norm_targets.get(ac, 0.0),
                        "rationale": rat
                    })
            continue

        total_sub_val = sum(h["current_value"] for h in sub_holdings)

        for h in sub_holdings:
            ticker = h["ticker"]
            price = h["current_price"]
            curr_shares = h["shares"]
            curr_val = h["current_value"]

            # Weight within asset class
            weight_in_class = (curr_val / total_sub_val) if total_sub_val > 0 else (1.0 / len(sub_holdings))
            holding_target_delta = round(delta * weight_in_class, 2)

            action = "HOLD"
            shares_to_trade = 0
            order_value = 0.0

            # Special case for cash reserve ticker
            if ticker in ("INR_CASH", "CASH"):
                if holding_target_delta > 100:
                    action = "BUY"  # Deposit cash
                    order_value = holding_target_delta
                    shares_to_trade = int(holding_target_delta)
                elif holding_target_delta < -100:
                    action = "SELL"  # Withdraw / deploy cash
                    order_value = abs(holding_target_delta)
                    shares_to_trade = int(order_value)
            else:
                if holding_target_delta > (price * 0.5):
                    action = "BUY"
                    shares_to_trade = int(math.floor(holding_target_delta / price))
                    order_value = round(shares_to_trade * price, 2)
                    if shares_to_trade <= 0:
                        action = "HOLD"
                elif holding_target_delta < -(price * 0.5):
                    action = "SELL"
                    shares_to_trade = int(math.floor(abs(holding_target_delta) / price))
                    if shares_to_trade > curr_shares:
                        shares_to_trade = int(curr_shares)
                    order_value = round(shares_to_trade * price, 2)
                    if shares_to_trade <= 0:
                        action = "HOLD"

            if action == "BUY":
                total_buy_value += order_value
                post_shares = curr_shares + shares_to_trade
                post_val = round(curr_val + order_value, 2)
            elif action == "SELL":
                total_sell_value += order_value
                post_shares = curr_shares - shares_to_trade
                post_val = round(curr_val - order_value, 2)
            else:
                post_shares = curr_shares
                post_val = curr_val

            post_pct = round((post_val / new_total * 100.0) if new_total > 0 else 0.0, 2)
            holding_curr_pct = round((curr_val / current_total * 100.0) if current_total > 0 else 0.0, 2)
            holding_drift = round(holding_curr_pct - norm_targets.get(ac, 0.0), 2)

            rat = generate_trade_rationale(
                action=action,
                ticker=ticker,
                asset_class=ac,
                current_pct=holding_curr_pct,
                target_pct=norm_targets.get(ac, 0.0),
                drift_pct=holding_drift
            )

            orders.append({
                "ticker": ticker,
                "name": h["name"],
                "asset_class": ac,
                "action": action,
                "current_shares": curr_shares,
                "shares_to_trade": shares_to_trade,
                "post_trade_shares": post_shares,
                "unit_price": price,
                "unit_price_formatted": format_inr(price),
                "order_value": order_value,
                "order_value_formatted": format_inr(order_value),
                "current_value": curr_val,
                "current_value_formatted": format_inr(curr_val),
                "post_trade_value": post_val,
                "post_trade_value_formatted": format_inr(post_val),
                "post_trade_pct": post_pct,
                "target_pct": norm_targets.get(ac, 0.0),
                "rationale": rat
            })

    total_buy_value = round(total_buy_value, 2)
    total_sell_value = round(total_sell_value, 2)
    net_cash_required = round(total_buy_value - total_sell_value, 2)
    unallocated_cash = round(cash_infusion - net_cash_required, 2)

    # Calculate post-rebalance asset class allocations
    post_class_summary = []
    for ac, target_pct in norm_targets.items():
        ac_orders = [o for o in orders if o["asset_class"] == ac]
        ac_post_val = sum(o["post_trade_value"] for o in ac_orders)
        ac_post_pct = round((ac_post_val / new_total * 100.0) if new_total > 0 else 0.0, 2)
        residual_drift = round(ac_post_pct - target_pct, 2)
        post_class_summary.append({
            "asset_class": ac,
            "target_pct": target_pct,
            "post_rebalance_pct": ac_post_pct,
            "post_rebalance_val": ac_post_val,
            "post_rebalance_val_formatted": format_inr(ac_post_val),
            "residual_drift_pct": residual_drift
        })

    return {
        "status": "success",
        "current_total_value": current_total,
        "current_total_value_formatted": format_inr(current_total),
        "cash_infusion": cash_infusion,
        "cash_infusion_formatted": format_inr(cash_infusion),
        "new_total_value": new_total,
        "new_total_value_formatted": format_inr(new_total),
        "total_buy_value": total_buy_value,
        "total_buy_value_formatted": format_inr(total_buy_value),
        "total_sell_value": total_sell_value,
        "total_sell_value_formatted": format_inr(total_sell_value),
        "net_cash_required": net_cash_required,
        "net_cash_required_formatted": format_inr(net_cash_required),
        "unallocated_cash_remaining": unallocated_cash,
        "unallocated_cash_formatted": format_inr(unallocated_cash),
        "inflow_rebalancing_efficiency": "High" if cash_infusion > 0 and total_sell_value < total_buy_value else "Standard",
        "orders": orders,
        "post_rebalance_asset_classes": post_class_summary
    }
