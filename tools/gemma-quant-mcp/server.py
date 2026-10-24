"""
FastAPI REST Server & Embedded Web Dashboard for Gemma Quant MCP.
Provides HTTP APIs and an interactive visual dashboard on port 8002.
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

app = FastAPI(
    title="Gemma Quant MCP & Invariant Engine",
    description="Certified Camarilla & Classic Pivot Engine, Double-Entry Invariants, and Gemma AI Theses.",
    version="1.0.0",
)


@app.get("/healthz")
def health_check():
    return {
        "status": "healthy",
        "service": "gemma-quant-mcp",
        "version": "1.0.0",
        "engine": "DalalDesk Quant + SettleUp Invariant Engine",
        "technologies": ["Gemma", "Gemini", "Model Context Protocol", "FastAPI"],
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
  <title>Gemma Quant MCP & Invariant Guardrails</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; }
    code, pre { font-family: 'JetBrains Mono', monospace; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen p-6 md:p-12">
  <div class="max-w-6xl mx-auto space-y-8">
    <header class="border-b border-slate-800 pb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-950/80 border border-cyan-500/30 text-cyan-400 text-xs font-semibold mb-3">
          <span>⚡ Google Open Source & AI Technologies</span>
        </div>
        <h1 class="text-3xl font-extrabold tracking-tight text-white">Gemma Quant MCP & Financial Invariants</h1>
        <p class="text-slate-400 mt-1">Certified Mathematical Pivot Engine, Double-Entry Zero-Sum Guardrails & Gemma AI Synthesizer</p>
      </div>
      <div class="flex items-center gap-3">
        <a href="/docs" class="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-sm font-semibold transition">API Docs (Swagger)</a>
        <a href="/healthz" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-sm font-semibold transition">/healthz</a>
      </div>
    </header>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <div class="text-cyan-400 font-bold mb-2 flex items-center gap-2">
          <span>📐</span> Certified Quant Algorithms
        </div>
        <p class="text-sm text-slate-400">Classic & Camarilla pivots (H4, H3, L3, L4), ATR volatility bounds, and Fibonacci 1.618 extensions computed deterministically.</p>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <div class="text-emerald-400 font-bold mb-2 flex items-center gap-2">
          <span>🛡️</span> Financial Invariant Guardrails
        </div>
        <p class="text-sm text-slate-400">Guarantees double-entry zero-sum cash flows (Σ Δ ≡ 0.00), allocation completeness (100%), and IEEE 754 precision protection.</p>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <div class="text-purple-400 font-bold mb-2 flex items-center gap-2">
          <span>🤖</span> Gemma AI Thesis & MCP Server
        </div>
        <p class="text-sm text-slate-400">Exposes standard JSON-RPC tools to AI agent workflows and synthesizes structural trade rationale with Google Gemma/Gemini.</p>
      </div>
    </div>

    <div class="bg-slate-900/60 border border-slate-800 rounded-xl p-6 space-y-4">
      <h2 class="text-xl font-bold text-white">Quick Test via cURL</h2>
      <pre class="bg-slate-950 p-4 rounded-lg text-xs text-cyan-300 overflow-x-auto border border-slate-800">
curl -X POST http://localhost:8002/api/quant/targets \\
  -H "Content-Type: application/json" \\
  -d '{"symbol": "RELIANCE", "ltp": 2985.4, "high": 3010.0, "low": 2960.0, "close": 2975.0}'
      </pre>
    </div>
  </div>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
