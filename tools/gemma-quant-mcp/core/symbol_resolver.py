"""
Generic Stock Symbol Resolver using Google Gemma / Gemini LLM & Exchange Search.
Translates any user input (company name, fuzzy keywords, partial ticker)
into the exact official NSE/BSE equity ticker.
"""

from __future__ import annotations
import os
import json
import httpx
from typing import Tuple, Optional, Dict

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# DalalDesk Curated Alias Map for rapid 0ms resolution
COMMON_ALIASES: Dict[str, str] = {
    "APAR": "APARINDS",
    "APARIND": "APARINDS",
    "APARINDUSTRIES": "APARINDS",
    "HFCL": "HFCL",
    "HIMACHAL": "HFCL",
    "AIRTEL": "BHARTIARTL",
    "BHARTI": "BHARTIARTL",
    "SUZLON": "SUZLON",
    "IREDA": "IREDA",
    "IRFC": "IRFC",
    "ZOMATO": "ZOMATO",
    "PAYTM": "PAYTM",
    "JIO": "JIOFIN",
    "JIOFIN": "JIOFIN",
    "TATAPOWER": "TATAPOWER",
    "TATA POWER": "TATAPOWER",
    "TATA MOTORS": "TATAMOTORS",
    "TATA": "TATAMOTORS",
    "TCS": "TCS",
    "INFOSYS": "INFY",
    "INFY": "INFY",
    "SBI": "SBIN",
    "STATE BANK": "SBIN",
    "STATEBANK": "SBIN",
    "HDFC": "HDFCBANK",
    "HDFCBANK": "HDFCBANK",
    "ICICI": "ICICIBANK",
    "ICICIBANK": "ICICIBANK",
    "RELIANCE": "RELIANCE",
    "AMBANI": "RELIANCE",
    "ADANI": "ADANIENT",
    "ADANIENTERPRISES": "ADANIENT",
    "ITC": "ITC",
    "L&T": "LT",
    "LT": "LT",
    "LARSEN": "LT",
}


def resolve_with_gemma(query: str, api_key: Optional[str] = None) -> Optional[str]:
    """
    Uses Gemma / Gemini LLM to interpret ambiguous natural language queries into an NSE ticker.
    """
    key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        return None

    prompt = f"""
You are an expert equity market data assistant for the Indian National Stock Exchange (NSE).
The user searched for: "{query}".
Identify the most relevant official Indian NSE stock ticker symbol (e.g., 'APAR' -> 'APARINDS', 'tata power' -> 'TATAPOWER', 'zomato' -> 'ZOMATO', 'hfcl' -> 'HFCL', 'reliance' -> 'RELIANCE').
Return ONLY a JSON object: {{"ticker": "EXACT_TICKER_SYMBOL", "name": "Company Name"}}
Do NOT output markdown fences, only raw JSON.
"""
    for mod in ["gemini-2.5-flash", "gemini-1.5-flash"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    parsed = json.loads(raw)
                    sym = parsed.get("ticker", "").strip().upper()
                    if sym:
                        return sym.replace(".NS", "").replace(".BO", "")
        except Exception:
            continue
    return None


def resolve_with_exchange_search(query: str) -> Optional[str]:
    """
    Searches live exchange database for the user query, prioritizing Indian .NS and .BO listings.
    """
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=8&newsCount=0"
    try:
        with httpx.Client(timeout=3.5, headers=HEADERS) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                quotes = resp.json().get("quotes", [])
                # 1. First priority: Indian listings (.NS or .BO)
                for q in quotes:
                    sym = q.get("symbol", "")
                    if sym.endswith(".NS") or sym.endswith(".BO"):
                        return sym.replace(".NS", "").replace(".BO", "")
                # 2. Second priority: exact match or top global ticker
                if quotes:
                    return quotes[0].get("symbol", "").replace(".NS", "").replace(".BO", "")
    except Exception:
        pass
    return None


def resolve_smart_ticker(user_input: str) -> Tuple[str, str]:
    """
    Resolves user input using Gemma LLM -> Live Exchange Search -> Alias Table.
    Returns (cleaned_symbol, resolution_method)
    """
    raw = user_input.strip()
    norm = raw.upper()

    # 1. Instant check in Curated Aliases
    if norm in COMMON_ALIASES:
        return COMMON_ALIASES[norm], "ALGORITHMIC_ALIAS"

    # Clean space variations
    cleaned_key = norm.replace(" ", "")
    if cleaned_key in COMMON_ALIASES:
        return COMMON_ALIASES[cleaned_key], "ALGORITHMIC_ALIAS"

    # 2. Live Exchange Search
    found = resolve_with_exchange_search(raw)
    if found:
        return found, "EXCHANGE_SEARCH_LIVE"

    # 3. Gemma / Gemini LLM reasoning
    llm_symbol = resolve_with_gemma(raw)
    if llm_symbol:
        return llm_symbol, "GEMMA_LLM_REASONING"

    # Fallback to normalized raw input
    return norm, "DIRECT_SYMBOL"
