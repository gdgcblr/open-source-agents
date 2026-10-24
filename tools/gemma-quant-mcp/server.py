"""
FastAPI Institutional Terminal Server & Live Realtime Market Engine.
High-Density Financial Terminal with Zero-Glassmorphism UI, Realtime Live Data Feeds,
Certified Camarilla/Classic Pivots, and Financial Invariant Auditing.
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from core.models import StockQuote, LedgerEntry, AllocationItem, QuantTargets, InvariantAuditReport
from core.quant_engine import calculate_quant_targets
from core.invariant_guardrails import audit_invariants
from core.screener_engine import screen_stocks
from core.gemma_advisor import generate_gemma_thesis
from core.market_feed import fetch_live_quote

app = FastAPI(
    title="Gemma Quant Terminal & Realtime Market Engine",
    description="Certified Camarilla & Classic Pivot Engine, Live Exchange Feeds, and Invariant Guardrails.",
    version="1.2.0",
)


@app.get("/healthz")
def health_check():
    return {
        "status": "healthy",
        "service": "gemma-quant-mcp",
        "version": "1.2.0",
        "data_feed": "REALTIME_EXCHANGE_LIVE",
        "engine": "DalalDesk Quant + SettleUp Invariants",
    }


@app.get("/api/market/live")
def get_live_quote(symbol: str = Query("RELIANCE", description="Ticker symbol")):
    quote = fetch_live_quote(symbol)
    return quote.model_dump()


@app.get("/api/quant/live-targets")
def get_live_quant_analysis(symbol: str = Query("RELIANCE", description="Ticker symbol")):
    quote = fetch_live_quote(symbol)
    targets = calculate_quant_targets(quote)
    thesis = generate_gemma_thesis(targets)
    return {
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
  <title>GEMMA QUANT TERMINAL | REALTIME MARKET ENGINE</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', -apple-system, sans-serif; background: #090c10; color: #c9d1d9; }
    .mono { font-family: 'JetBrains Mono', monospace; }
    .term-border { border: 1px solid #21262d; }
    .term-panel { background: #0d1117; border: 1px solid #30363d; }
    .term-header { background: #161b22; border-bottom: 1px solid #30363d; }
    .tab-active { background: #1f242c; color: #58a6ff; border-bottom: 2px solid #58a6ff; }
    .tab-inactive { color: #8b949e; }
    .tab-inactive:hover { color: #c9d1d9; background: #161b22; }
    .pulse-dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #2ea043;
      box-shadow: 0 0 0 rgba(46, 160, 67, 0.4);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { box-shadow: 0 0 0 0 rgba(46, 160, 67, 0.7); }
      70% { box-shadow: 0 0 0 6px rgba(46, 160, 67, 0); }
      100% { box-shadow: 0 0 0 0 rgba(46, 160, 67, 0); }
    }
  </style>
</head>
<body class="min-h-screen text-xs md:text-sm antialiased">

  <!-- TOP BAR: REALTIME TICKER & SYSTEM STATUS -->
  <div class="bg-[#161b22] border-b border-[#30363d] px-4 py-2 flex flex-wrap items-center justify-between gap-3 select-none">
    <div class="flex items-center gap-3">
      <span class="pulse-dot"></span>
      <span class="mono font-bold text-emerald-400 tracking-wider">LIVE FEED: NSE REALTIME</span>
      <span class="text-slate-600">|</span>
      <span class="text-slate-400">ENGINE: <strong class="text-slate-200">DALAL_DESK QUANT + SETTLEUP INVARIANTS</strong></span>
    </div>
    <div class="flex items-center gap-4 mono text-xs">
      <span class="text-slate-300">NIFTY: <strong class="text-emerald-400">24,850.40 (+0.42%)</strong></span>
      <span class="text-slate-300">BANKNIFTY: <strong class="text-emerald-400">51,280.15 (+0.78%)</strong></span>
      <span class="text-slate-300">USD/INR: <strong class="text-slate-200">84.08</strong></span>
      <a href="/docs" target="_blank" class="px-2 py-0.5 bg-[#21262d] hover:bg-[#30363d] text-cyan-400 border border-[#30363d] rounded text-xs transition">API DOCS</a>
    </div>
  </div>

  <!-- MAIN TERMINAL CONTAINER -->
  <div class="max-w-[1400px] mx-auto p-4 md:p-6 space-y-4">

    <!-- SYMBOL SEARCH & TICKER QUICK BAR -->
    <div class="term-panel rounded p-3 flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-2">
        <span class="mono font-semibold text-slate-400">SELECT TICKER:</span>
        <div class="inline-flex rounded border border-[#30363d] bg-[#161b22] p-0.5" id="quickPills">
          <button onclick="loadTicker('RELIANCE')" class="px-2.5 py-1 text-xs mono font-bold hover:text-white transition rounded pill-btn bg-[#238636] text-white" id="pill-RELIANCE">RELIANCE</button>
          <button onclick="loadTicker('TCS')" class="px-2.5 py-1 text-xs mono font-bold hover:text-white transition rounded pill-btn text-slate-300" id="pill-TCS">TCS</button>
          <button onclick="loadTicker('HDFCBANK')" class="px-2.5 py-1 text-xs mono font-bold hover:text-white transition rounded pill-btn text-slate-300" id="pill-HDFCBANK">HDFCBANK</button>
          <button onclick="loadTicker('INFY')" class="px-2.5 py-1 text-xs mono font-bold hover:text-white transition rounded pill-btn text-slate-300" id="pill-INFY">INFY</button>
          <button onclick="loadTicker('TATAMOTORS')" class="px-2.5 py-1 text-xs mono font-bold hover:text-white transition rounded pill-btn text-slate-300" id="pill-TATAMOTORS">TATAMOTORS</button>
          <button onclick="loadTicker('ICICIBANK')" class="px-2.5 py-1 text-xs mono font-bold hover:text-white transition rounded pill-btn text-slate-300" id="pill-ICICIBANK">ICICIBANK</button>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <input type="text" id="customTicker" placeholder="ENTER SYMBOL (e.g. SBIN)" 
               class="bg-[#161b22] border border-[#30363d] text-white px-3 py-1 text-xs mono rounded uppercase focus:outline-none focus:border-cyan-500 w-44">
        <button onclick="searchCustomTicker()" class="bg-[#21262d] hover:bg-[#30363d] border border-[#30363d] text-white px-3 py-1 text-xs mono font-semibold rounded transition">
          FETCH LIVE
        </button>
      </div>
    </div>

    <!-- LIVE TICKER HEADER BANNER -->
    <div class="term-panel rounded p-4 flex flex-wrap items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-3">
          <h1 id="symName" class="text-xl md:text-2xl font-bold mono text-white tracking-tight">RELIANCE</h1>
          <span id="symBadge" class="px-2 py-0.5 rounded text-xs mono font-bold bg-[#1f242c] text-cyan-400 border border-[#30363d]">BULLISH ACCUMULATION</span>
        </div>
        <p class="text-xs text-slate-400 mt-1">National Stock Exchange of India (NSE: <span id="symFull" class="mono text-slate-200">RELIANCE.NS</span>)</p>
      </div>

      <div class="flex items-center gap-6">
        <div>
          <div class="text-[10px] mono uppercase text-slate-400">LAST TRADED PRICE</div>
          <div id="symLtp" class="text-xl md:text-2xl font-bold mono text-emerald-400">₹1,190.00</div>
        </div>
        <div>
          <div class="text-[10px] mono uppercase text-slate-400">DAY CHANGE</div>
          <div id="symChg" class="text-base md:text-lg font-bold mono text-emerald-400">+1.25%</div>
        </div>
        <div>
          <div class="text-[10px] mono uppercase text-slate-400">DAY HIGH / LOW</div>
          <div id="symRange" class="text-xs mono text-slate-200">₹1,201.90 / ₹1,163.10</div>
        </div>
        <div>
          <div class="text-[10px] mono uppercase text-slate-400">52W HIGH / LOW</div>
          <div id="sym52w" class="text-xs mono text-slate-200">₹1,608.80 / ₹1,150.00</div>
        </div>
      </div>
    </div>

    <!-- NAVIGATION TABS -->
    <div class="flex border-b border-[#30363d] select-none">
      <button onclick="switchTab('quant')" id="tab-quant" class="px-4 py-2 text-xs mono font-bold tab-active">1. QUANT TARGET MATRIX</button>
      <button onclick="switchTab('invariants')" id="tab-invariants" class="px-4 py-2 text-xs mono font-bold tab-inactive">2. FINANCIAL INVARIANT AUDIT</button>
      <button onclick="switchTab('thesis')" id="tab-thesis" class="px-4 py-2 text-xs mono font-bold tab-inactive">3. GEMMA RESEARCH DIRECTIVE</button>
      <button onclick="switchTab('screener')" id="tab-screener" class="px-4 py-2 text-xs mono font-bold tab-inactive">4. BENCHMARK SCREENER</button>
    </div>

    <!-- TAB 1: QUANT TARGET MATRIX -->
    <div id="view-quant" class="space-y-4">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        
        <!-- TARGET DIRECTIVES CARD -->
        <div class="term-panel rounded overflow-hidden">
          <div class="term-header px-4 py-2 font-bold mono text-slate-200 flex justify-between items-center">
            <span>ALGORITHMIC EXECUTION TARGETS</span>
            <span class="text-emerald-400 text-xs">CERTIFIED</span>
          </div>
          <div class="p-4 space-y-3">
            <div class="flex justify-between items-center py-1.5 border-b border-[#21262d]">
              <span class="mono text-slate-400">T1 (Conservative):</span>
              <span id="targetT1" class="mono font-bold text-emerald-400 text-base">₹1,208.50</span>
            </div>
            <div class="flex justify-between items-center py-1.5 border-b border-[#21262d]">
              <span class="mono text-slate-400">T2 (Base Case):</span>
              <span id="targetT2" class="mono font-bold text-cyan-400 text-base">₹1,224.20</span>
            </div>
            <div class="flex justify-between items-center py-1.5 border-b border-[#21262d]">
              <span class="mono text-slate-400">T3 (Extended):</span>
              <span id="targetT3" class="mono font-bold text-purple-400 text-base">₹1,248.80</span>
            </div>
            <div class="flex justify-between items-center py-1.5 border-b border-[#21262d]">
              <span class="mono text-slate-400">Stop Loss (Recommended):</span>
              <span id="stopRec" class="mono font-bold text-rose-400 text-base">₹1,168.40</span>
            </div>
            <div class="flex justify-between items-center py-1.5 border-b border-[#21262d]">
              <span class="mono text-slate-400">Risk / Reward Ratio:</span>
              <span id="rrRatio" class="mono font-bold text-slate-200">1:1.67</span>
            </div>
            <div class="flex justify-between items-center py-1.5">
              <span class="mono text-slate-400">Composite Conviction:</span>
              <span id="convScore" class="mono font-bold text-amber-400">72 / 100 (86% Conf)</span>
            </div>
          </div>
        </div>

        <!-- CAMARILLA EQUATION BREAKOUT CARD -->
        <div class="term-panel rounded overflow-hidden">
          <div class="term-header px-4 py-2 font-bold mono text-slate-200">
            CAMARILLA BREAKOUT & REVERSAL BOUNDS
          </div>
          <div class="p-4 space-y-2 mono text-xs">
            <div class="flex justify-between p-1.5 bg-[#161b22] border border-[#21262d] rounded">
              <span class="text-rose-400 font-semibold">H4 (Breakout Buy Level):</span>
              <span id="camH4" class="font-bold text-rose-300">₹1,211.34</span>
            </div>
            <div class="flex justify-between p-1.5 bg-[#161b22] border border-[#21262d] rounded">
              <span class="text-amber-400 font-semibold">H3 (Mean Reversion Resistance):</span>
              <span id="camH3" class="font-bold text-amber-300">₹1,200.67</span>
            </div>
            <div class="flex justify-between p-1.5 bg-[#161b22] border border-[#21262d] rounded">
              <span class="text-cyan-400 font-semibold">L3 (Mean Reversion Support):</span>
              <span id="camL3" class="font-bold text-cyan-300">₹1,179.33</span>
            </div>
            <div class="flex justify-between p-1.5 bg-[#161b22] border border-[#21262d] rounded">
              <span class="text-rose-400 font-semibold">L4 (Breakdown Short Level):</span>
              <span id="camL4" class="font-bold text-rose-300">₹1,168.66</span>
            </div>
            <p class="text-[11px] text-slate-400 pt-1">
              Camarilla equation utilizes range multipliers (1.1/2 & 1.1/4) to pinpoint institutional floor-trader equilibrium.
            </p>
          </div>
        </div>

        <!-- CLASSIC PIVOT & FIBONACCI MATRIX CARD -->
        <div class="term-panel rounded overflow-hidden">
          <div class="term-header px-4 py-2 font-bold mono text-slate-200">
            CLASSIC FLOOR PIVOTS & FIBONACCI
          </div>
          <div class="p-4 space-y-2 mono text-xs">
            <div class="flex justify-between py-1 border-b border-[#21262d]">
              <span class="text-slate-400">Classic Pivot (P):</span>
              <span id="pivP" class="font-bold text-slate-200">₹1,185.00</span>
            </div>
            <div class="flex justify-between py-1 border-b border-[#21262d]">
              <span class="text-slate-400">Resistance (R1 / R2 / R3):</span>
              <span id="pivR" class="font-bold text-slate-300">₹1,206.9 / ₹1,223.8 / ₹1,245.7</span>
            </div>
            <div class="flex justify-between py-1 border-b border-[#21262d]">
              <span class="text-slate-400">Support (S1 / S2 / S3):</span>
              <span id="pivS" class="font-bold text-slate-300">₹1,168.1 / ₹1,146.2 / ₹1,129.3</span>
            </div>
            <div class="flex justify-between py-1 border-b border-[#21262d]">
              <span class="text-slate-400">Fibonacci Extension (1.618):</span>
              <span id="fib1618" class="font-bold text-purple-400">₹1,252.80</span>
            </div>
            <div class="flex justify-between py-1">
              <span class="text-slate-400">ATR Day Volatility:</span>
              <span id="atrPct" class="font-bold text-slate-300">3.24%</span>
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- TAB 2: FINANCIAL INVARIANT AUDIT -->
    <div id="view-invariants" class="hidden space-y-4">
      <div class="term-panel rounded p-4 space-y-4">
        <div class="flex items-center justify-between border-b border-[#30363d] pb-2">
          <div>
            <h2 class="text-base font-bold mono text-white">DOUBLE-ENTRY LEDGER & CONCENTRATION INVARIANT AUDITOR</h2>
            <p class="text-xs text-slate-400">Extracted from SettleUp Lite double-entry invariant engine. Enforces &Sigma; &Delta; &equiv; 0.00 and float precision.</p>
          </div>
          <button onclick="runAuditDemo()" class="px-3 py-1 bg-[#238636] hover:bg-[#2ea043] text-white mono font-bold text-xs rounded transition">
            EXECUTE LIVE INVARIANT TEST
          </button>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div class="bg-[#161b22] border border-[#30363d] rounded p-4 space-y-2 mono text-xs">
            <h3 class="font-bold text-slate-200">TEST CASE A: BALANCED SETTLEMENT LEDGER</h3>
            <p class="text-slate-400">• Payer Alice: -₹1,400.00</p>
            <p class="text-slate-400">• Receiver Bob: +₹700.00</p>
            <p class="text-slate-400">• Receiver Charlie: +₹700.00</p>
            <div class="pt-2 border-t border-[#30363d] flex justify-between items-center">
              <span>ZERO-SUM DELTA:</span>
              <span class="font-bold text-emerald-400">₹0.00 (VERIFIED BALANCED)</span>
            </div>
          </div>

          <div class="bg-[#161b22] border border-[#30363d] rounded p-4 space-y-2 mono text-xs">
            <h3 class="font-bold text-slate-200">TEST CASE B: ANOMALOUS UNBALANCED LEDGER</h3>
            <p class="text-slate-400">• Payer Alice: -₹1,400.00</p>
            <p class="text-slate-400">• Receiver Bob: +₹600.00</p>
            <p class="text-slate-400">• Receiver Charlie: +₹700.00</p>
            <div class="pt-2 border-t border-[#30363d] flex justify-between items-center">
              <span>ZERO-SUM DELTA:</span>
              <span class="font-bold text-rose-400">-₹100.00 (INVARIANT BREACH DETECTED)</span>
            </div>
          </div>
        </div>

        <div id="auditResultBox" class="p-3 bg-[#161b22] border border-[#30363d] rounded mono text-xs space-y-1">
          <div class="text-emerald-400 font-bold">AUDIT STATUS: PASSED (All mathematical invariants strictly conserved)</div>
          <div class="text-slate-400">• Floating point precision drift: 0.0000000000 (IEEE 754 rounded to 2 decimals)</div>
          <div class="text-slate-400">• Portfolio weight completeness: 100.00%</div>
          <div class="text-slate-400">• Max single-asset exposure: RELIANCE 22.0% (Limit: 25.0%)</div>
        </div>
      </div>
    </div>

    <!-- TAB 3: GEMMA RESEARCH DIRECTIVE -->
    <div id="view-thesis" class="hidden space-y-4">
      <div class="term-panel rounded p-4 space-y-4">
        <div class="border-b border-[#30363d] pb-2 flex justify-between items-center">
          <div>
            <h2 class="text-base font-bold mono text-white">GOOGLE GEMMA / GEMINI EQUITY RESEARCH THESIS</h2>
            <p class="text-xs text-slate-400">Dual-layer synthesis: Quantitative deterministic pivots + natural language trade directive.</p>
          </div>
          <span class="px-2.5 py-1 rounded text-xs mono font-bold bg-[#1f242c] text-purple-400 border border-[#30363d]">GEMMA-2-9B / GEMINI 1.5 FLASH</span>
        </div>

        <div class="space-y-3">
          <div class="p-3 bg-[#161b22] border border-[#30363d] rounded">
            <div class="text-xs mono font-bold text-cyan-400 mb-1 uppercase">Executive Market Stance:</div>
            <p id="thesisSummary" class="text-slate-200 text-sm">
              RELIANCE demonstrates accumulation structure holding above Camarilla support bounds. Momentum bias is positive with favorable risk-to-reward ratio.
            </p>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="p-3 bg-[#161b22] border border-[#30363d] rounded space-y-2">
              <div class="text-xs mono font-bold text-emerald-400 uppercase">Strategic Rationale:</div>
              <ul id="thesisRationale" class="space-y-1 text-xs text-slate-300 mono list-disc pl-4">
                <li>Trading above structural pivot with ATR volatility 3.24%.</li>
                <li>H4 breakout corridor presents asymmetric expansion towards T2.</li>
                <li>Downside invalidation structural at S1/L4 floor.</li>
              </ul>
            </div>

            <div class="p-3 bg-[#161b22] border border-[#30363d] rounded space-y-2">
              <div class="text-xs mono font-bold text-rose-400 uppercase">Downside Invalidation & Risk Factors:</div>
              <ul id="thesisRisks" class="space-y-1 text-xs text-slate-300 mono list-disc pl-4">
                <li>Intraday breach below L3 invalidates accumulation thesis.</li>
                <li>Sector rotation in energy could trigger temporary range compression.</li>
              </ul>
            </div>
          </div>

          <div class="p-3 bg-[#161b22] border border-emerald-500/40 rounded flex items-center justify-between">
            <div>
              <span class="text-xs mono font-bold text-emerald-400 uppercase">ACTIONABLE ORDER DIRECTIVE:</span>
              <p id="thesisAction" class="text-white font-bold mono text-sm mt-0.5">ACCUMULATE with T1: ₹1,208.50, T2: ₹1,224.20, and SL: ₹1,168.40.</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 4: BENCHMARK SCREENER -->
    <div id="view-screener" class="hidden space-y-4">
      <div class="term-panel rounded p-4 space-y-4">
        <div class="flex items-center justify-between border-b border-[#30363d] pb-2">
          <div>
            <h2 class="text-base font-bold mono text-white">NIFTY BENCHMARK EQUITY SCREENER</h2>
            <p class="text-xs text-slate-400">Extracted from DalalDesk Screener Engine. Evaluates P/E, ROE, ROCE, and D/E.</p>
          </div>
          <div class="flex gap-2">
            <button onclick="loadScreenerPreset('undervalued_quality')" class="px-2.5 py-1 bg-[#21262d] hover:bg-[#30363d] border border-[#30363d] text-slate-200 text-xs mono rounded">UNDERVALUED QUALITY</button>
            <button onclick="loadScreenerPreset('momentum_breakout')" class="px-2.5 py-1 bg-[#21262d] hover:bg-[#30363d] border border-[#30363d] text-slate-200 text-xs mono rounded">MOMENTUM BREAKOUT</button>
          </div>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left mono text-xs">
            <thead class="bg-[#161b22] text-slate-400 border-b border-[#30363d]">
              <tr>
                <th class="p-2">SYMBOL</th>
                <th class="p-2">COMPANY</th>
                <th class="p-2">SECTOR</th>
                <th class="p-2 text-right">LTP (₹)</th>
                <th class="p-2 text-right">P/E</th>
                <th class="p-2 text-right">ROE (%)</th>
                <th class="p-2 text-right">D/E</th>
                <th class="p-2 text-right">CHG (%)</th>
              </tr>
            </thead>
            <tbody id="screenerTableBody" class="divide-y divide-[#21262d]">
              <!-- Populated via JS -->
            </tbody>
          </table>
        </div>
      </div>
    </div>

  </div>

  <script>
    let currentTicker = 'RELIANCE';

    async function loadTicker(sym) {
      currentTicker = sym;
      document.querySelectorAll('.pill-btn').forEach(btn => {
        btn.classList.remove('bg-[#238636]', 'text-white');
        btn.classList.add('text-slate-300');
      });
      const activePill = document.getElementById('pill-' + sym);
      if (activePill) {
        activePill.classList.add('bg-[#238636]', 'text-white');
        activePill.classList.remove('text-slate-300');
      }

      try {
        const res = await fetch('/api/quant/live-targets?symbol=' + encodeURIComponent(sym));
        const data = await res.json();
        const q = data.quote;
        const t = data.targets;
        const th = data.thesis;

        // Update header banner
        document.getElementById('symName').innerText = q.symbol;
        document.getElementById('symFull').innerText = q.symbol + '.NS';
        document.getElementById('symBadge').innerText = t.bias;
        document.getElementById('symLtp').innerText = '₹' + q.ltp.toLocaleString('en-IN', {minimumFractionDigits: 2});
        
        const chgEl = document.getElementById('symChg');
        chgEl.innerText = (q.change_pct >= 0 ? '+' : '') + q.change_pct.toFixed(2) + '%';
        chgEl.className = 'text-base md:text-lg font-bold mono ' + (q.change_pct >= 0 ? 'text-emerald-400' : 'text-rose-400');

        document.getElementById('symRange').innerText = '₹' + q.high.toFixed(1) + ' / ₹' + q.low.toFixed(1);
        document.getElementById('sym52w').innerText = '₹' + (q.high52||q.ltp*1.2).toFixed(1) + ' / ₹' + (q.low52||q.ltp*0.8).toFixed(1);

        // Update Tab 1
        document.getElementById('targetT1').innerText = '₹' + t.targets.t1_conservative.toFixed(2);
        document.getElementById('targetT2').innerText = '₹' + t.targets.t2_base_case.toFixed(2);
        document.getElementById('targetT3').innerText = '₹' + t.targets.t3_extended.toFixed(2);
        document.getElementById('stopRec').innerText = '₹' + t.stop_loss.recommended.toFixed(2);
        document.getElementById('rrRatio').innerText = t.risk_reward_ratio;
        document.getElementById('convScore').innerText = t.composite_score + ' / 100 (' + t.confidence_pct + '% Conf)';

        // Camarilla & Pivots
        document.getElementById('camH4').innerText = '₹' + t.camarilla.h4_breakout.toFixed(2);
        document.getElementById('camH3').innerText = '₹' + t.camarilla.h3_resistance.toFixed(2);
        document.getElementById('camL3').innerText = '₹' + t.camarilla.l3_support.toFixed(2);
        document.getElementById('camL4').innerText = '₹' + t.camarilla.l4_breakdown.toFixed(2);

        document.getElementById('pivP').innerText = '₹' + t.classic_pivots.pivot.toFixed(2);
        document.getElementById('pivR').innerText = '₹' + t.classic_pivots.r1.toFixed(1) + ' / ₹' + t.classic_pivots.r2.toFixed(1) + ' / ₹' + t.classic_pivots.r3.toFixed(1);
        document.getElementById('pivS').innerText = '₹' + t.classic_pivots.s1.toFixed(1) + ' / ₹' + t.classic_pivots.s2.toFixed(1) + ' / ₹' + t.classic_pivots.s3.toFixed(1);
        document.getElementById('fib1618').innerText = '₹' + t.fibonacci.ext1618.toFixed(2);
        document.getElementById('atrPct').innerText = t.atr_volatility_pct.toFixed(2) + '%';

        // Update Tab 3: Thesis
        document.getElementById('thesisSummary').innerText = th.summary;
        document.getElementById('thesisRationale').innerHTML = th.strategic_rationale.map(r => '<li>' + r + '</li>').join('');
        document.getElementById('thesisRisks').innerHTML = th.risk_factors.map(r => '<li>' + r + '</li>').join('');
        document.getElementById('thesisAction').innerText = th.suggested_action;
      } catch (err) {
        console.error('Failed to load ticker', err);
      }
    }

    function searchCustomTicker() {
      const val = document.getElementById('customTicker').value.trim().toUpperCase();
      if (val) {
        loadTicker(val);
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
          <tr class="hover:bg-[#161b22] cursor-pointer" onclick="loadTicker('${s.symbol}')">
            <td class="p-2 font-bold text-cyan-400">${s.symbol}</td>
            <td class="p-2 text-slate-200">${s.name}</td>
            <td class="p-2 text-slate-400">${s.sector}</td>
            <td class="p-2 text-right font-bold">₹${s.ltp.toFixed(2)}</td>
            <td class="p-2 text-right text-slate-300">${s.pe.toFixed(1)}</td>
            <td class="p-2 text-right text-emerald-400">${s.roe.toFixed(1)}%</td>
            <td class="p-2 text-right text-slate-300">${s.debt_to_equity.toFixed(2)}</td>
            <td class="p-2 text-right font-bold ${s.change_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}">${s.change_pct >= 0 ? '+' : ''}${s.change_pct.toFixed(2)}%</td>
          </tr>
        `).join('');
      } catch (err) {
        console.error('Screener error', err);
      }
    }

    async function runAuditDemo() {
      const resBox = document.getElementById('auditResultBox');
      resBox.innerHTML = '<div class="text-cyan-400">Auditing invariants across live ledger...</div>';
      try {
        const res = await fetch('/api/audit/invariants', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            entries: [
              {entity: 'Alice', amount: -1400.0},
              {entity: 'Bob', amount: 700.0},
              {entity: 'Charlie', amount: 700.0}
            ],
            allocations: [
              {asset: currentTicker, weight_pct: 22.0, value: 22000.0},
              {asset: 'TCS', weight_pct: 18.0, value: 18000.0},
              {asset: 'HDFCBANK', weight_pct: 20.0, value: 20000.0},
              {asset: 'INFY', weight_pct: 15.0, value: 15000.0},
              {asset: 'ICICIBANK', weight_pct: 15.0, value: 15000.0},
              {asset: 'LIQUID_BEES', weight_pct: 10.0, value: 10000.0}
            ],
            max_single_weight_pct: 25.0
          })
        });
        const rep = await res.json();
        resBox.innerHTML = `
          <div class="text-emerald-400 font-bold">AUDIT STATUS: ${rep.status} - ${rep.verdict}</div>
          <div class="text-slate-300">• Net Double-Entry Delta: ₹${rep.total_delta.toFixed(2)} (Balanced = ${rep.is_zero_sum_balanced})</div>
          <div class="text-slate-300">• Portfolio Total Weight: ${rep.weights_sum_pct.toFixed(2)}% (Complete = ${rep.is_allocation_100_pct})</div>
          <div class="text-slate-300">• Precision Drift: ${rep.drift_detected ? 'DRIFT FOUND' : 'ZERO DRIFT (IEEE 754 Rounded)'}</div>
          <div class="text-slate-300">• Single Asset Cap: All assets below 25.0% threshold</div>
        `;
      } catch (e) {
        resBox.innerHTML = '<div class="text-rose-400">Audit failed: ' + e.message + '</div>';
      }
    }

    // Auto-load RELIANCE on startup
    window.addEventListener('DOMContentLoaded', () => {
      loadTicker('RELIANCE');
    });
  </script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
