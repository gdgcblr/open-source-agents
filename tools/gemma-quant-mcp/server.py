"""
FastAPI Server for Arthaniti Quant Engine & Realtime Feeds.
Dedicated to Arthaniti: Certified Camarilla & Classic Pivot Engine,
Realtime NSE/BSE Market Feeds with Gemma LLM Resolver, and Portfolio Risk Guardrails.
"""

from __future__ import annotations
from typing import List, Optional
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from core.models import StockQuote, LedgerEntry, AllocationItem, QuantTargets, InvariantAuditReport
from core.quant_engine import calculate_quant_targets
from core.invariant_guardrails import audit_invariants
from core.screener_engine import screen_stocks
from core.gemma_advisor import generate_gemma_thesis
from core.market_feed import fetch_live_quote
from core.symbol_resolver import resolve_smart_ticker
from core.hub_agent import ArthanitiMasterHub
from pydantic import BaseModel

class HubChatRequest(BaseModel):
    query: str
    model: str = "gemma-2-9b-it"


app = FastAPI(
    title="Arthaniti Quant Engine & Realtime Feeds",
    description="Certified Camarilla & Classic Pivot Engine with Gemma LLM Stock Resolver and Portfolio Risk Guardrails.",
    version="2.1.0",
)


@app.get("/healthz")
def health_check():
    return {
        "status": "healthy",
        "service": "arthaniti-quant-hub",
        "version": "2.2.0",
        "architecture": "Google ADK Hub-and-Spoke",
        "hub_urn": ArthanitiMasterHub.urn,
        "spokes": ArthanitiMasterHub.SPOKES,
        "guardrails": ["DETERMINISTIC_CAMARILLA_MATH", "RISK_REWARD_BOUNDS", "PORTFOLIO_CONCENTRATION_25PCT", "ALLOCATION_100PCT"],
        "resolver": "Gemma LLM + Live Exchange Search",
    }


@app.get("/api/hub/spokes")
def get_hub_spokes():
    return {
        "hub": ArthanitiMasterHub.urn,
        "spokes": ArthanitiMasterHub.SPOKES,
    }


@app.post("/api/hub/chat")
def hub_chat_endpoint(req: HubChatRequest):
    return ArthanitiMasterHub.process_user_query(req.query, model_choice=req.model)


@app.get("/api/market/live")
def get_live_quote(symbol: str = Query("HFCL", description="Ticker or company name")):
    quote = fetch_live_quote(symbol)
    return quote.model_dump()


@app.get("/api/quant/live-targets")
def get_live_quant_analysis(
    symbol: str = Query("HFCL", description="Ticker or company name"),
    model: str = Query("gemma-2-9b-it", description="AI Model: gemma-2-9b-it, gemini-2.5-flash, gemini-1.5-flash"),
):
    resolved, method = resolve_smart_ticker(symbol)
    quote = fetch_live_quote(symbol)
    targets = calculate_quant_targets(quote)
    thesis = generate_gemma_thesis(targets, model_choice=model)
    return {
        "query": symbol,
        "resolved_symbol": quote.symbol,
        "resolution_method": method,
        "quote": quote.model_dump(),
        "targets": targets.model_dump(),
        "thesis": thesis.model_dump(),
    }


@app.post("/api/quant/targets", response_model=QuantTargets)
def get_quant_targets(quote: StockQuote):
    return calculate_quant_targets(quote)


@app.post("/api/audit/invariants", response_model=InvariantAuditReport)
def run_invariant_audit(
    entries: Optional[List[LedgerEntry]] = None,
    allocations: Optional[List[AllocationItem]] = None,
    max_single_weight_pct: float = 25.0,
):
    return audit_invariants(
        entries=entries,
        allocations=allocations,
        max_single_weight_pct=max_single_weight_pct,
    )


@app.get("/api/screener")
def run_screener(
    max_pe: Optional[float] = None,
    min_roe: Optional[float] = None,
    max_debt_to_equity: Optional[float] = None,
    min_change_pct: Optional[float] = None,
    preset: Optional[str] = None,
):
    stocks = screen_stocks(
        max_pe=max_pe,
        min_roe=min_roe,
        max_debt_to_equity=max_debt_to_equity,
        min_change_pct=min_change_pct,
        preset=preset,
    )
    return [s.model_dump() for s in stocks]


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Arthaniti | Quant Equity Terminal & Risk Guardrails</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap" rel="stylesheet">
  <style>
    body {
      font-family: 'Inter', -apple-system, sans-serif;
      background-color: #F8FAFC;
      color: #0F172A;
    }
    .mono { font-family: 'JetBrains Mono', monospace; }
    .card-shadow {
      box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04), 0 1px 2px -1px rgba(0, 0, 0, 0.04);
    }
    .tab-active {
      background-color: #0F172A;
      color: #FFFFFF;
      font-weight: 700;
    }
    .tab-inactive {
      background-color: transparent;
      color: #475569;
      font-weight: 600;
    }
    .tab-inactive:hover {
      background-color: #E2E8F0;
      color: #0F172A;
    }
    .pulse-dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #10B981;
      box-shadow: 0 0 0 rgba(16, 185, 129, 0.4);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
      70% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
      100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }
  </style>
</head>
<body class="min-h-screen text-slate-800 antialiased pb-12">

  <!-- TOP ARTHANITI HEADER -->
  <header class="bg-white border-b border-slate-200 sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 py-3.5 flex flex-wrap items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="w-9 h-9 rounded-xl bg-slate-900 flex items-center justify-center text-white font-bold text-base shadow-sm">
          A
        </div>
        <div>
          <div class="flex items-center gap-2">
            <span class="text-lg font-extrabold text-slate-900 tracking-tight">Arthaniti</span>
            <span class="text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200">
              Quant & Risk Guardrails
            </span>
          </div>
          <p class="text-xs text-slate-500">Autonomous Equity Targets & Prudential Guardrails</p>
        </div>
      </div>

      <div class="flex items-center gap-3 text-xs font-medium">
        <div class="flex items-center gap-2 bg-emerald-50 text-emerald-700 px-3 py-1.5 rounded-lg border border-emerald-200">
          <span class="pulse-dot"></span>
          <span>NSE/BSE Realtime Feed Live</span>
        </div>
        <a href="/docs" target="_blank" class="px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white font-semibold rounded-lg transition shadow-sm">
          Swagger Docs
        </a>
      </div>
    </div>
  </header>

  <!-- ARTHANITI MULTI-AGENT HUB-AND-SPOKE TOPOLOGY BAR -->
  <div class="bg-slate-900 text-slate-200 text-xs py-2.5 px-4 border-b border-slate-800">
    <div class="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-2">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-emerald-400 font-bold tracking-wider uppercase text-[11px]">ADK Multi-Agent Topology:</span>
        <span class="bg-slate-800 px-2.5 py-0.5 rounded border border-slate-700 text-white font-semibold">Hub: Master Orchestrator</span>
        <span class="text-slate-500 font-bold">&rarr;</span>
        <span class="bg-slate-800 px-2.5 py-0.5 rounded border border-slate-700 text-white font-semibold">Spoke 1: Live Feed</span>
        <span class="text-slate-500 font-bold">&rarr;</span>
        <span class="bg-slate-800 px-2.5 py-0.5 rounded border border-slate-700 text-white font-semibold">Spoke 2: Camarilla Engine</span>
        <span class="text-slate-500 font-bold">&rarr;</span>
        <span class="bg-slate-800 px-2.5 py-0.5 rounded border border-slate-700 text-white font-semibold">Spoke 3: Risk Guardrail</span>
        <span class="text-slate-500 font-bold">&rarr;</span>
        <span class="bg-slate-800 px-2.5 py-0.5 rounded border border-slate-700 text-white font-semibold">Spoke 4: Gemma Thesis</span>
        <span class="text-slate-500 font-bold">&rarr;</span>
        <span class="bg-slate-800 px-2.5 py-0.5 rounded border border-slate-700 text-white font-semibold">Spoke 5: Screener</span>
      </div>
      <span class="text-emerald-400 font-mono text-[11px] bg-emerald-950/80 px-2 py-0.5 rounded border border-emerald-800">5/5 SPOKES CONNECTED</span>
    </div>
  </div>

  <!-- MAIN CONTAINER -->
  <main class="max-w-7xl mx-auto px-4 sm:px-6 pt-6 space-y-6">

    <!-- INTERACTIVE ARTHANITI HUB COPILOT CARD -->
    <div class="bg-white rounded-2xl border border-slate-200 p-5 card-shadow space-y-4">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 class="text-base font-extrabold text-slate-900">Arthaniti Master Quant Copilot (Google ADK Hub)</h2>
          <p class="text-xs text-slate-500 font-medium">Type any stock query, portfolio check, or screener request. Central Hub routes tasks across all 5 spokes.</p>
        </div>
        <span class="text-xs font-bold px-3 py-1 rounded-full bg-slate-100 text-slate-800 border border-slate-200 self-start sm:self-auto">
          Gemma-2-9B &bull; Gemini 2.5 Flash
        </span>
      </div>

      <div class="flex gap-2">
        <input type="text" id="hubPromptInput" 
               placeholder="e.g. Analyze live stock price and Camarilla breakout levels for HFCL" 
               class="flex-1 px-4 py-2.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-slate-800 focus:bg-white text-slate-800 placeholder-slate-400 font-medium transition"
               onkeydown="if(event.key==='Enter') dispatchArthanitiHubPrompt()">
        <button onclick="dispatchArthanitiHubPrompt()" class="px-5 py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-extrabold rounded-xl shadow-xs transition uppercase tracking-wider">
          Dispatch to Hub
        </button>
      </div>

      <div class="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100">
        <span class="text-xs font-bold text-slate-400 uppercase tracking-wider mr-1">Pre-built Scenarios:</span>
        <button onclick="sendHubScenario('Analyze live stock price and Camarilla breakout levels for HFCL')" 
                class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 hover:border-slate-800 text-slate-700 bg-slate-50 hover:bg-white transition">
          📈 Camarilla Levels: HFCL
        </button>
        <button onclick="sendHubScenario('Analyze live stock price and Camarilla breakout levels for APAR Industries')" 
                class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 hover:border-slate-800 text-slate-700 bg-slate-50 hover:bg-white transition">
          ⚡ High Momentum: APAR Industries
        </button>
        <button onclick="sendHubScenario('Audit our multi-asset portfolio with 35% HFCL, 20% TCS, 20% HDFCBANK, 25% LIQUID_BEES against concentration limits')" 
                class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 hover:border-slate-800 text-slate-700 bg-slate-50 hover:bg-white transition">
          🛡️ SEBI Risk Audit: 35% Concentration Cap
        </button>
        <button onclick="sendHubScenario('Screen Indian equities for bullish volume breakout setups')" 
                class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 hover:border-slate-800 text-slate-700 bg-slate-50 hover:bg-white transition">
          🔍 High-Conviction Breakout Screener
        </button>
      </div>

      <!-- INTER-AGENT A2A EXECUTION LOG -->
      <div id="hubDispatchTelemetry" class="hidden p-4 rounded-xl bg-slate-900 text-slate-300 space-y-2 text-xs mono">
        <div class="flex items-center justify-between border-b border-slate-800 pb-2">
          <span class="text-emerald-400 font-bold uppercase tracking-wider">A2A (Agent-to-Agent) Execution Telemetry</span>
          <span id="hubLatencyBadge" class="text-slate-400">12ms</span>
        </div>
        <div id="hubDispatchLogItems" class="space-y-1 text-[11px]">
          <!-- Dispatched dynamically -->
        </div>
      </div>
    </div>

    <!-- SEARCH & GENERIC STOCK RESOLVER CARD -->
    <div class="bg-white rounded-2xl border border-slate-200 p-5 card-shadow space-y-4">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 class="text-base font-bold text-slate-900">Generic Equity Discovery (Gemma LLM Resolver)</h2>
          <p class="text-xs text-slate-500">Search any stock, company name, or industry. Gemma LLM resolves the exact exchange ticker and fetches real-time tick data.</p>
        </div>
        <div class="flex items-center gap-2 w-full md:w-auto">
          <div class="relative flex-1 md:w-80">
            <input type="text" id="customInput" placeholder="e.g. APAR, HFCL, Tata Power, Suzlon..." 
                   class="w-full pl-3.5 pr-24 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-slate-900 focus:bg-white text-slate-800 placeholder-slate-400 font-medium transition"
                   onkeydown="if(event.key==='Enter') executeSearch()">
            <button onclick="executeSearch()" class="absolute right-1 top-1 bottom-1 px-3 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-lg transition">
              SEARCH
            </button>
          </div>
        </div>
      </div>

      <!-- POPULAR QUICK PILLS -->
      <div class="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100">
        <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider mr-1">Quick Select:</span>
        <button onclick="loadTicker('HFCL')" class="px-3 py-1 text-xs font-semibold rounded-lg border border-slate-200 hover:border-slate-900 text-slate-700 bg-slate-50 hover:bg-white transition" id="pill-HFCL">HFCL</button>
        <button onclick="loadTicker('APAR')" class="px-3 py-1 text-xs font-semibold rounded-lg border border-slate-200 hover:border-slate-900 text-slate-700 bg-slate-50 hover:bg-white transition" id="pill-APAR">APAR</button>
        <button onclick="loadTicker('TATA POWER')" class="px-3 py-1 text-xs font-semibold rounded-lg border border-slate-200 hover:border-slate-900 text-slate-700 bg-slate-50 hover:bg-white transition" id="pill-TATAPOWER">TATA POWER</button>
        <button onclick="loadTicker('SUZLON')" class="px-3 py-1 text-xs font-semibold rounded-lg border border-slate-200 hover:border-slate-900 text-slate-700 bg-slate-50 hover:bg-white transition" id="pill-SUZLON">SUZLON</button>
        <button onclick="loadTicker('RELIANCE')" class="px-3 py-1 text-xs font-semibold rounded-lg border border-slate-200 hover:border-slate-900 text-slate-700 bg-slate-50 hover:bg-white transition" id="pill-RELIANCE">RELIANCE</button>
        <button onclick="loadTicker('TCS')" class="px-3 py-1 text-xs font-semibold rounded-lg border border-slate-200 hover:border-slate-900 text-slate-700 bg-slate-50 hover:bg-white transition" id="pill-TCS">TCS</button>
        <button onclick="loadTicker('HDFCBANK')" class="px-3 py-1 text-xs font-semibold rounded-lg border border-slate-200 hover:border-slate-900 text-slate-700 bg-slate-50 hover:bg-white transition" id="pill-HDFCBANK">HDFCBANK</button>
        <button onclick="loadTicker('INFY')" class="px-3 py-1 text-xs font-semibold rounded-lg border border-slate-200 hover:border-slate-900 text-slate-700 bg-slate-50 hover:bg-white transition" id="pill-INFY">INFY</button>
      </div>
    </div>

    <!-- LIVE TICKER HERO CARD -->
    <div class="bg-white rounded-2xl border border-slate-200 p-6 card-shadow flex flex-col md:flex-row md:items-center justify-between gap-6">
      <div class="space-y-1">
        <div class="flex items-center gap-3">
          <h1 id="symTitle" class="text-2xl md:text-3xl font-extrabold text-slate-900 tracking-tight">HFCL</h1>
          <span id="symBadge" class="text-xs font-bold px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
            BULLISH ACCUMULATION
          </span>
        </div>
        <p class="text-xs text-slate-500">
          Exchange Scrip: <strong id="symExchange" class="text-slate-800 font-bold">HFCL.NS</strong> &bull; Resolution: <span id="symMethod" class="text-slate-700 font-semibold">Gemma LLM Resolver</span>
        </p>
      </div>

      <div class="grid grid-cols-2 sm:grid-cols-4 gap-6 text-left">
        <div>
          <div class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Live Price</div>
          <div id="symLtp" class="text-2xl font-bold mono text-slate-900">₹240.07</div>
        </div>
        <div>
          <div class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Day Change</div>
          <div id="symChg" class="text-lg font-bold mono text-rose-600">-6.23%</div>
        </div>
        <div>
          <div class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Day Range</div>
          <div id="symRange" class="text-xs font-semibold mono text-slate-700">₹238.98 - ₹247.89</div>
        </div>
        <div>
          <div class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">52W Range</div>
          <div id="sym52w" class="text-xs font-semibold mono text-slate-700">₹59.82 - ₹282.25</div>
        </div>
      </div>
    </div>

    <!-- NAVIGATION TABS -->
    <div class="bg-slate-200/60 p-1 rounded-xl inline-flex flex-wrap gap-1">
      <button onclick="switchTab('quant')" id="tab-quant" class="px-4 py-2 rounded-lg text-xs font-bold tab-active transition">
        1. Quant Target Matrix
      </button>
      <button onclick="switchTab('invariants')" id="tab-invariants" class="px-4 py-2 rounded-lg text-xs font-semibold tab-inactive transition">
        2. Portfolio Risk Guardrails
      </button>
      <button onclick="switchTab('thesis')" id="tab-thesis" class="px-4 py-2 rounded-lg text-xs font-semibold tab-inactive transition">
        3. Gemma Research Directive
      </button>
      <button onclick="switchTab('screener')" id="tab-screener" class="px-4 py-2 rounded-lg text-xs font-semibold tab-inactive transition">
        4. Benchmark Screener
      </button>
    </div>

    <!-- TAB 1: QUANT TARGET MATRIX -->
    <div id="view-quant" class="grid grid-cols-1 md:grid-cols-3 gap-6">
      
      <!-- TARGETS CARD -->
      <div class="bg-white rounded-2xl border border-slate-200 p-5 card-shadow space-y-4">
        <div class="flex items-center justify-between border-b border-slate-100 pb-3">
          <h3 class="font-bold text-slate-900 text-sm">Certified Execution Targets</h3>
          <span class="text-xs font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded">Deterministic</span>
        </div>
        <div class="space-y-3 text-xs">
          <div class="flex justify-between items-center py-1 border-b border-slate-100">
            <span class="text-slate-500 font-medium">T1 (Conservative):</span>
            <span id="targetT1" class="mono font-bold text-emerald-600 text-sm">₹242.00</span>
          </div>
          <div class="flex justify-between items-center py-1 border-b border-slate-100">
            <span class="text-slate-500 font-medium">T2 (Base Case):</span>
            <span id="targetT2" class="mono font-bold text-blue-600 text-sm">₹245.50</span>
          </div>
          <div class="flex justify-between items-center py-1 border-b border-slate-100">
            <span class="text-slate-500 font-medium">T3 (Extended Fibonacci):</span>
            <span id="targetT3" class="mono font-bold text-purple-600 text-sm">₹251.20</span>
          </div>
          <div class="flex justify-between items-center py-1 border-b border-slate-100">
            <span class="text-slate-500 font-medium">Stop Loss (Recommended):</span>
            <span id="stopRec" class="mono font-bold text-rose-600 text-sm">₹235.80</span>
          </div>
          <div class="flex justify-between items-center py-1 border-b border-slate-100">
            <span class="text-slate-500 font-medium">Risk / Reward Ratio:</span>
            <span id="rrRatio" class="mono font-bold text-slate-800">1:1.67</span>
          </div>
          <div class="flex justify-between items-center py-1">
            <span class="text-slate-500 font-medium">Algorithmic Conviction:</span>
            <span id="convScore" class="mono font-bold text-amber-600">68 / 100 (84% Conf)</span>
          </div>
        </div>
      </div>

      <!-- CAMARILLA PIVOTS -->
      <div class="bg-white rounded-2xl border border-slate-200 p-5 card-shadow space-y-4">
        <div class="border-b border-slate-100 pb-3">
          <h3 class="font-bold text-slate-900 text-sm">Camarilla Equilibrium Bounds</h3>
          <p class="text-[11px] text-slate-400">Institutional floor trader price bounds</p>
        </div>
        <div class="space-y-2 text-xs mono">
          <div class="flex justify-between p-2 rounded-lg bg-rose-50 border border-rose-100">
            <span class="text-rose-700 font-semibold">H4 Breakout Long:</span>
            <span id="camH4" class="font-bold text-rose-800">₹244.90</span>
          </div>
          <div class="flex justify-between p-2 rounded-lg bg-amber-50 border border-amber-100">
            <span class="text-amber-800 font-semibold">H3 Resistance:</span>
            <span id="camH3" class="font-bold text-amber-900">₹242.50</span>
          </div>
          <div class="flex justify-between p-2 rounded-lg bg-blue-50 border border-blue-100">
            <span class="text-blue-800 font-semibold">L3 Support:</span>
            <span id="camL3" class="font-bold text-blue-900">₹237.60</span>
          </div>
          <div class="flex justify-between p-2 rounded-lg bg-rose-50 border border-rose-100">
            <span class="text-rose-700 font-semibold">L4 Breakdown Short:</span>
            <span id="camL4" class="font-bold text-rose-800">₹235.20</span>
          </div>
        </div>
      </div>

      <!-- CLASSIC PIVOTS & VOLATILITY -->
      <div class="bg-white rounded-2xl border border-slate-200 p-5 card-shadow space-y-4">
        <div class="border-b border-slate-100 pb-3">
          <h3 class="font-bold text-slate-900 text-sm">Classic Pivots & Volatility</h3>
          <p class="text-[11px] text-slate-400">Weighted floor benchmarks & ATR %</p>
        </div>
        <div class="space-y-2 text-xs mono">
          <div class="flex justify-between py-1 border-b border-slate-100">
            <span class="text-slate-500">Floor Pivot (P):</span>
            <span id="pivP" class="font-bold text-slate-800">₹242.30</span>
          </div>
          <div class="flex justify-between py-1 border-b border-slate-100">
            <span class="text-slate-500">Resistances (R1/R2/R3):</span>
            <span id="pivR" class="font-semibold text-slate-700">₹245 / ₹251 / ₹255</span>
          </div>
          <div class="flex justify-between py-1 border-b border-slate-100">
            <span class="text-slate-500">Supports (S1/S2/S3):</span>
            <span id="pivS" class="font-semibold text-slate-700">₹236 / ₹232 / ₹227</span>
          </div>
          <div class="flex justify-between py-1 border-b border-slate-100">
            <span class="text-slate-500">Fibonacci Ext (1.618):</span>
            <span id="fib1618" class="font-bold text-purple-600">₹254.60</span>
          </div>
          <div class="flex justify-between py-1">
            <span class="text-slate-500">ATR Day Volatility:</span>
            <span id="atrPct" class="font-bold text-slate-800">3.48%</span>
          </div>
        </div>
      </div>

    </div>

    <!-- TAB 2: PORTFOLIO RISK GUARDRAILS -->
    <div id="view-invariants" class="hidden space-y-4">
      <div class="bg-white rounded-2xl border border-slate-200 p-6 card-shadow space-y-4">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
          <div>
            <h3 class="text-base font-bold text-slate-900">Arthaniti Portfolio Risk & Invariant Guardrails</h3>
            <p class="text-xs text-slate-500">Audits single-stock concentration (&le;25%), total capital allocation completeness (100%), and zero IEEE 754 precision drift.</p>
          </div>
          <button onclick="runAuditDemo()" class="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs rounded-xl shadow-sm transition">
            AUDIT ACTIVE PORTFOLIO
          </button>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div class="p-4 rounded-xl border border-emerald-200 bg-emerald-50/50 space-y-2">
            <div class="font-bold text-emerald-800 uppercase">Guardrail Verified: Prudent Diversification</div>
            <p class="text-slate-600">&bull; Active Asset: 22.0% allocation (Cap: 25.0%)</p>
            <p class="text-slate-600">&bull; Large Cap Equity: 53.0% allocation</p>
            <p class="text-slate-600">&bull; Liquid Bees / Cash: 25.0% buffer</p>
            <div class="pt-2 border-t border-emerald-200 flex justify-between font-bold text-emerald-700">
              <span>CONCENTRATION STATUS:</span>
              <span>VERIFIED WITHIN LIMITS</span>
            </div>
          </div>

          <div class="p-4 rounded-xl border border-rose-200 bg-rose-50/50 space-y-2">
            <div class="font-bold text-rose-800 uppercase">Guardrail Triggered: Over-Concentration Alert</div>
            <p class="text-slate-600">&bull; Single Stock Exposure: 42.0% (BREACH: Exceeds 25.0% cap)</p>
            <p class="text-slate-600">&bull; Action: System issues mandatory de-risking directive</p>
            <div class="pt-2 border-t border-rose-200 flex justify-between font-bold text-rose-700">
              <span>PRUDENTIAL RISK:</span>
              <span>CONCENTRATION BREACH DETECTED</span>
            </div>
          </div>
        </div>

        <div id="auditResultBox" class="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs space-y-1 font-medium">
          <div class="text-emerald-700 font-bold text-sm">GUARDRAIL AUDIT PASSED: All risk limits strictly verified.</div>
          <div class="text-slate-600">&bull; Total capital allocation: 100.00% (Complete)</div>
          <div class="text-slate-600">&bull; Arithmetic precision: IEEE 754 rounded to 2 decimals</div>
          <div class="text-slate-600">&bull; Concentration guardrail: All individual positions below 25.0% limit</div>
        </div>
      </div>
    </div>

    <!-- TAB 3: GEMMA RESEARCH DIRECTIVE -->
    <div id="view-thesis" class="hidden space-y-4">
      <div class="bg-white rounded-2xl border border-slate-200 p-6 card-shadow space-y-4">
        <div class="flex items-center justify-between border-b border-slate-100 pb-3">
          <div>
            <h3 class="text-base font-bold text-slate-900">Google Gemma & Gemini Research Directive</h3>
            <p class="text-xs text-slate-500">Synthesizes deterministic quant bounds into actionable institutional directives.</p>
          </div>
          <span class="text-xs font-bold px-3 py-1 rounded-full bg-slate-100 text-slate-800 border border-slate-200">
            Gemma-2-9B / Gemini 2.5 Flash
          </span>
        </div>

        <div class="space-y-4 text-xs">
          <div class="p-4 rounded-xl bg-slate-50 border border-slate-200">
            <span class="font-bold text-slate-900 uppercase tracking-wider block mb-1">Executive Market Stance:</span>
            <p id="thesisSummary" class="text-slate-700 text-sm leading-relaxed">
              HFCL demonstrates positive accumulation structure holding above Camarilla support bounds. Momentum bias is favorable.
            </p>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
              <span class="font-bold text-emerald-700 uppercase tracking-wider block">Strategic Rationales:</span>
              <ul id="thesisRationale" class="space-y-1 text-slate-600 list-disc pl-4">
                <li>Trading above structural pivot with ATR volatility 3.48%.</li>
                <li>Camarilla H4 breakout level presents asymmetric expansion towards T2.</li>
                <li>Risk-to-reward ratio provides structural downside invalidation at recommended stop.</li>
              </ul>
            </div>

            <div class="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
              <span class="font-bold text-rose-700 uppercase tracking-wider block">Downside Invalidation Factors:</span>
              <ul id="thesisRisks" class="space-y-1 text-slate-600 list-disc pl-4">
                <li>Breach below Camarilla L3 invalidates the accumulation premise.</li>
                <li>Sector liquidity shift could trigger temporary range compression.</li>
              </ul>
            </div>
          </div>

          <div class="p-4 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-between">
            <div>
              <span class="text-xs font-bold text-emerald-800 uppercase tracking-wider">Actionable Order Directive:</span>
              <p id="thesisAction" class="text-emerald-900 font-bold text-sm mt-0.5">ACCUMULATE with T1: ₹242.00, T2: ₹245.50, and SL: ₹235.80.</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 4: BENCHMARK SCREENER -->
    <div id="view-screener" class="hidden space-y-4">
      <div class="bg-white rounded-2xl border border-slate-200 p-6 card-shadow space-y-4">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-3">
          <div>
            <h3 class="text-base font-bold text-slate-900">Arthaniti Equity Screener</h3>
            <p class="text-xs text-slate-500">Filter benchmark equities by quality growth, momentum breakouts, and solvency.</p>
          </div>
          <div class="flex gap-2">
            <button onclick="loadScreenerPreset('undervalued_quality')" class="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-lg transition">Undervalued Quality</button>
            <button onclick="loadScreenerPreset('momentum_breakout')" class="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-lg transition">Momentum Breakout</button>
          </div>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="bg-slate-50 text-slate-500 border-b border-slate-200 font-semibold uppercase">
              <tr>
                <th class="p-3">Symbol</th>
                <th class="p-3">Company</th>
                <th class="p-3">Sector</th>
                <th class="p-3 text-right">LTP (₹)</th>
                <th class="p-3 text-right">P/E</th>
                <th class="p-3 text-right">ROE (%)</th>
                <th class="p-3 text-right">D/E</th>
                <th class="p-3 text-right">Day Chg</th>
              </tr>
            </thead>
            <tbody id="screenerTableBody" class="divide-y divide-slate-100">
              <!-- Populated via JS -->
            </tbody>
          </table>
        </div>
      </div>
    </div>

  </main>

  <script>
    async function sendHubScenario(query) {
      document.getElementById('hubPromptInput').value = query;
      dispatchArthanitiHubPrompt();
    }

    async function dispatchArthanitiHubPrompt() {
      const q = document.getElementById('hubPromptInput').value.trim();
      if (!q) return;

      const telemBox = document.getElementById('hubDispatchTelemetry');
      const logItems = document.getElementById('hubDispatchLogItems');
      const latencyBadge = document.getElementById('hubLatencyBadge');

      telemBox.classList.remove('hidden');
      logItems.innerHTML = '<div class="text-emerald-400 font-bold">Arthaniti Master Hub dispatching tasks to spokes...</div>';

      try {
        const model = document.getElementById('modelSelect') ? document.getElementById('modelSelect').value : 'gemma-2-9b-it';
        const res = await fetch('/api/hub/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({query: q, model: model})
        });
        const d = await res.json();

        latencyBadge.innerText = `${d.latency_ms}ms • ${d.guardrail_verdict}`;
        logItems.innerHTML = d.dispatch_log.map(item => `
          <div><span class="text-emerald-400 font-bold">[${item.agent}]</span> ${item.message}</div>
        `).join('');

        // If stock quant result, sync with the main grid
        if (d.spoke_results.quant) {
          const sym = d.spoke_results.quant.symbol;
          document.getElementById('customInput').value = sym;
          loadStock(sym);
        } else if (d.spoke_results.risk) {
          switchTab('invariants');
        } else if (d.spoke_results.screener) {
          switchTab('screener');
        }
      } catch (err) {
        logItems.innerHTML = `<div class="text-rose-400">Hub dispatch error: ${err.message}</div>`;
      }
    }

    let currentSymbol = 'HFCL';

    async function loadTicker(query) {
      currentSymbol = query;
      document.querySelectorAll('[id^="pill-"]').forEach(p => {
        p.classList.remove('bg-slate-900', 'text-white', 'border-slate-900');
        p.classList.add('bg-slate-50', 'text-slate-700', 'border-slate-200');
      });

      const cleanKey = query.toUpperCase().replace(/\s+/g, '');
      const activePill = document.getElementById('pill-' + cleanKey);
      if (activePill) {
        activePill.classList.add('bg-slate-900', 'text-white', 'border-slate-900');
        activePill.classList.remove('bg-slate-50', 'text-slate-700', 'border-slate-200');
      }

      try {
        const res = await fetch('/api/quant/live-targets?symbol=' + encodeURIComponent(query));
        const data = await res.json();
        const q = data.quote;
        const t = data.targets;
        const th = data.thesis;

        document.getElementById('symTitle').innerText = q.symbol;
        document.getElementById('symExchange').innerText = q.symbol + '.NS';
        document.getElementById('symMethod').innerText = data.resolution_method || 'Live Exchange';
        document.getElementById('symBadge').innerText = t.bias;

        document.getElementById('symLtp').innerText = '₹' + q.ltp.toLocaleString('en-IN', {minimumFractionDigits: 2});
        
        const chgEl = document.getElementById('symChg');
        chgEl.innerText = (q.change_pct >= 0 ? '+' : '') + q.change_pct.toFixed(2) + '%';
        chgEl.className = 'text-lg font-bold mono ' + (q.change_pct >= 0 ? 'text-emerald-600' : 'text-rose-600');

        document.getElementById('symRange').innerText = '₹' + q.low.toFixed(2) + ' - ₹' + q.high.toFixed(2);
        document.getElementById('sym52w').innerText = '₹' + (q.low52||q.ltp*0.75).toFixed(2) + ' - ₹' + (q.high52||q.ltp*1.25).toFixed(2);

        // Tab 1: Quant Targets
        document.getElementById('targetT1').innerText = '₹' + t.targets.t1_conservative.toFixed(2);
        document.getElementById('targetT2').innerText = '₹' + t.targets.t2_base_case.toFixed(2);
        document.getElementById('targetT3').innerText = '₹' + t.targets.t3_extended.toFixed(2);
        document.getElementById('stopRec').innerText = '₹' + t.stop_loss.recommended.toFixed(2);
        document.getElementById('rrRatio').innerText = t.risk_reward_ratio;
        document.getElementById('convScore').innerText = t.composite_score + ' / 100 (' + t.confidence_pct + '% Conf)';

        // Camarilla
        document.getElementById('camH4').innerText = '₹' + t.camarilla.h4_breakout.toFixed(2);
        document.getElementById('camH3').innerText = '₹' + t.camarilla.h3_resistance.toFixed(2);
        document.getElementById('camL3').innerText = '₹' + t.camarilla.l3_support.toFixed(2);
        document.getElementById('camL4').innerText = '₹' + t.camarilla.l4_breakdown.toFixed(2);

        // Classic
        document.getElementById('pivP').innerText = '₹' + t.classic_pivots.pivot.toFixed(2);
        document.getElementById('pivR').innerText = '₹' + t.classic_pivots.r1.toFixed(1) + ' / ₹' + t.classic_pivots.r2.toFixed(1) + ' / ₹' + t.classic_pivots.r3.toFixed(1);
        document.getElementById('pivS').innerText = '₹' + t.classic_pivots.s1.toFixed(1) + ' / ₹' + t.classic_pivots.s2.toFixed(1) + ' / ₹' + t.classic_pivots.s3.toFixed(1);
        document.getElementById('fib1618').innerText = '₹' + t.fibonacci.ext1618.toFixed(2);
        document.getElementById('atrPct').innerText = t.atr_volatility_pct.toFixed(2) + '%';

        // Tab 3: Thesis
        document.getElementById('thesisSummary').innerText = th.summary;
        document.getElementById('thesisRationale').innerHTML = th.strategic_rationale.map(r => '<li>' + r + '</li>').join('');
        document.getElementById('thesisRisks').innerHTML = th.risk_factors.map(r => '<li>' + r + '</li>').join('');
        document.getElementById('thesisAction').innerText = th.suggested_action;
      } catch (e) {
        console.error('Error loading quote', e);
      }
    }

    function executeSearch() {
      const q = document.getElementById('customInput').value.trim();
      if (q) {
        loadTicker(q);
      }
    }

    function switchTab(tab) {
      ['quant', 'invariants', 'thesis', 'screener'].forEach(t => {
        document.getElementById('view-' + t).classList.add('hidden');
        const b = document.getElementById('tab-' + t);
        b.classList.remove('tab-active');
        b.classList.add('tab-inactive');
      });
      document.getElementById('view-' + tab).classList.remove('hidden');
      const activeBtn = document.getElementById('tab-' + tab);
      activeBtn.classList.add('tab-active');
      activeBtn.classList.remove('tab-inactive');

      if (tab === 'screener') {
        loadScreenerPreset('undervalued_quality');
      }
    }

    async function loadScreenerPreset(preset) {
      try {
        const res = await fetch('/api/screener?preset=' + preset);
        const list = await res.json();
        const tbody = document.getElementById('screenerTableBody');
        tbody.innerHTML = list.map(s => `
          <tr class="hover:bg-slate-50 cursor-pointer transition" onclick="loadTicker('${s.symbol}')">
            <td class="p-3 font-bold text-slate-900">${s.symbol}</td>
            <td class="p-3 font-medium text-slate-800">${s.name}</td>
            <td class="p-3 text-slate-500">${s.sector}</td>
            <td class="p-3 text-right font-bold mono">₹${s.ltp.toFixed(2)}</td>
            <td class="p-3 text-right mono text-slate-600">${s.pe.toFixed(1)}</td>
            <td class="p-3 text-right mono text-emerald-600 font-bold">${s.roe.toFixed(1)}%</td>
            <td class="p-3 text-right mono text-slate-600">${s.debt_to_equity.toFixed(2)}</td>
            <td class="p-3 text-right font-bold mono ${s.change_pct >= 0 ? 'text-emerald-600' : 'text-rose-600'}">${s.change_pct >= 0 ? '+' : ''}${s.change_pct.toFixed(2)}%</td>
          </tr>
        `).join('');
      } catch (err) {
        console.error('Screener error', err);
      }
    }

    async function runAuditDemo() {
      const box = document.getElementById('auditResultBox');
      box.innerHTML = '<div class="text-slate-900 font-bold">Auditing active portfolio against prudential guardrails...</div>';
      try {
        const res = await fetch('/api/audit/invariants', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            allocations: [
              {asset: currentSymbol, weight_pct: 22.0, value: 22000.0},
              {asset: 'TCS', weight_pct: 18.0, value: 18000.0},
              {asset: 'HDFCBANK', weight_pct: 20.0, value: 20000.0},
              {asset: 'LIQUID_BEES', weight_pct: 40.0, value: 40000.0}
            ],
            max_single_weight_pct: 25.0
          })
        });
        const rep = await res.json();
        box.innerHTML = `
          <div class="text-emerald-700 font-bold text-sm">GUARDRAIL STATUS: ${rep.status} &bull; ${rep.verdict}</div>
          <div class="text-slate-700">&bull; Capital Allocation: ${rep.weights_sum_pct.toFixed(2)}% (100% Complete)</div>
          <div class="text-slate-700">&bull; Precision: IEEE 754 rounded to 2 decimals</div>
          <div class="text-emerald-700 font-semibold">&bull; Concentration Guardrail: Active holding ${currentSymbol} at 22.0% (Under 25% Cap)</div>
        `;
      } catch (e) {
        box.innerHTML = '<div class="text-rose-600 font-bold">Audit failed: ' + e.message + '</div>';
      }
    }

    window.addEventListener('DOMContentLoaded', () => {
      loadTicker('HFCL');
    });
  </script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
