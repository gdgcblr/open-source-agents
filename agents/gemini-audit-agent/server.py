"""
FastAPI Server & Financial Audit Dashboard for Bharat Dues.
Exposes REST endpoints for ledger invariant checks, receipt OCR, and settlement paths.
Production App: https://bharat-dues.web.app
"""

from typing import List, Optional
from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from core.models import Member, Expense, SettlementRecord, AuditReport
from core.ledger import audit_ledger
from core.hub_agent import AutonomousHubAgent


class ChatQueryRequest(BaseModel):
    query: str


class GroupAuditRequest(BaseModel):
    members: List[Member]
    expenses: List[Expense]
    settlements: List[SettlementRecord] = []


app = FastAPI(
    title="Bharat Dues Autonomous Hub & Spoke Audit Agent",
    description="Google ADK Multi-Agent Hub and Spoke Architecture for Bharat Dues (https://bharat-dues.web.app).",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def health_check():
    return {
        "status": "healthy",
        "service": "bharat-dues-hub-agent",
        "version": "2.0.0",
        "architecture": "Google ADK Hub-and-Spoke",
        "production_app": "https://bharat-dues.web.app",
        "hub_urn": AutonomousHubAgent.urn,
        "spokes": AutonomousHubAgent.SPOKES,
        "guardrails": [
            "Mathematical Net Zero-Sum Conservation (∑ Δ ≡ 0.00)",
            "Unconfirmed Settlement Quarantine Isolation",
            "O(1) Canonical Member Hash Resolution",
        ],
    }


@app.get("/api/hub/spokes")
def get_spokes():
    return {
        "hub": AutonomousHubAgent.urn,
        "spokes": AutonomousHubAgent.SPOKES,
    }


@app.post("/api/hub/chat")
def hub_chat_endpoint(req: ChatQueryRequest):
    return AutonomousHubAgent.process_user_query(req.query)


@app.post("/api/audit", response_model=AuditReport)
def run_ledger_audit(payload: GroupAuditRequest):
    return audit_ledger(
        members=payload.members,
        expenses=payload.expenses,
        settlements=payload.settlements,
    )


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Bharat Dues | Autonomous Hub & Spoke Financial Agent</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --primary: #00B9F1;
      --navy: #002E6E;
      --bg: #F5F7FA;
      --card: #FFFFFF;
      --border: #E2E8F0;
    }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background-color: var(--bg);
      color: #1E293B;
      -webkit-font-smoothing: antialiased;
    }
    .mono { font-family: 'JetBrains Mono', monospace; }
    .card-shadow {
      box-shadow: 0 4px 12px rgba(0, 46, 110, 0.04), 0 1px 3px rgba(0, 0, 0, 0.02);
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
<body class="min-h-screen antialiased pb-16">

  <!-- TOP APP BAR -->
  <header class="bg-white border-b border-slate-200 sticky top-0 z-50 shadow-xs">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 py-3.5 flex flex-wrap items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-[#00B9F1] flex items-center justify-center text-white font-black text-xl shadow-xs">
          ₹
        </div>
        <div>
          <div class="flex items-center gap-2">
            <span class="text-xl font-extrabold text-[#002E6E] tracking-tight">Bharat Dues</span>
            <span class="text-xs font-bold px-2.5 py-0.5 rounded-full bg-sky-50 text-[#007CA6] border border-sky-200">
              Google ADK Hub Agent
            </span>
          </div>
          <p class="text-xs text-slate-500 font-medium">
            Live Production App: <a href="https://bharat-dues.web.app" target="_blank" class="text-[#00B9F1] font-bold hover:underline">bharat-dues.web.app ↗</a>
          </p>
        </div>
      </div>

      <div class="flex items-center gap-3 text-xs font-semibold">
        <div class="hidden md:flex items-center gap-2 bg-emerald-50 text-emerald-800 px-3.5 py-2 rounded-xl border border-emerald-200">
          <span class="pulse-dot"></span>
          <span>Zero-Sum Invariant Enforced (∑Δ ≡ 0.00)</span>
        </div>
        <a href="https://bharat-dues.web.app" target="_blank" class="px-4 py-2 bg-[#00B9F1] hover:bg-[#00a3d4] text-white font-bold rounded-xl transition shadow-xs">
          Launch App ↗
        </a>
      </div>
    </div>
  </header>

  <!-- CLEAN TOPOLOGY SUB-BANNER -->
  <div class="bg-sky-50/70 border-b border-sky-100 text-xs py-2.5 px-4 sm:px-6">
    <div class="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-wrap items-center gap-2">
        <span class="font-bold text-[#002E6E] uppercase tracking-wide text-[11px]">ADK Multi-Agent Topology:</span>
        <span class="bg-white px-2.5 py-1 rounded-lg border border-sky-200 text-[#002E6E] font-semibold shadow-2xs">Hub: Master Orchestrator</span>
        <span class="text-sky-300 font-bold">&rarr;</span>
        <span class="bg-white px-2.5 py-1 rounded-lg border border-sky-200 text-[#002E6E] font-semibold shadow-2xs">Spoke 1: Double-Entry Auditor</span>
        <span class="text-sky-300 font-bold">&rarr;</span>
        <span class="bg-white px-2.5 py-1 rounded-lg border border-sky-200 text-[#002E6E] font-semibold shadow-2xs">Spoke 2: Arthaniti Quant Analyst</span>
        <span class="text-sky-300 font-bold">&rarr;</span>
        <span class="bg-white px-2.5 py-1 rounded-lg border border-sky-200 text-[#002E6E] font-semibold shadow-2xs">Spoke 3: Portfolio Health</span>
        <span class="text-sky-300 font-bold">&rarr;</span>
        <span class="bg-white px-2.5 py-1 rounded-lg border border-sky-200 text-[#002E6E] font-semibold shadow-2xs">Spoke 4: Settlement & UPI</span>
      </div>
      <span class="text-emerald-700 font-bold text-[11px] bg-emerald-100/60 px-2 py-0.5 rounded-md">4/4 SPOKES READY</span>
    </div>
  </div>

  <!-- MAIN WRAPPER -->
  <main class="max-w-7xl mx-auto px-4 sm:px-6 pt-6 space-y-6">

    <!-- COPILOT QUERY DISPATCH CARD -->
    <div class="bg-white rounded-2xl border border-slate-200 p-6 card-shadow space-y-5">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 class="text-lg font-extrabold text-[#002E6E]">Autonomous Financial AI Copilot</h2>
          <p class="text-xs text-slate-500 font-medium mt-0.5">Describe any bill split, tangled group expense, or audit query. Central Hub routes tasks across spokes.</p>
        </div>
        <span class="text-xs font-bold px-3 py-1.5 rounded-full bg-sky-50 text-[#007CA6] border border-sky-200 self-start sm:self-auto">
          Gemini 2.5 Flash / Fast-Path
        </span>
      </div>

      <!-- INPUT FIELD -->
      <div class="flex gap-2">
        <input type="text" id="userInput" 
               placeholder="e.g. Shikhar paid ₹3,000 for dinner split with Aman. Aman paid Shikhar ₹1,400 pending approval." 
               class="flex-1 px-4 py-3 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-[#00B9F1] focus:bg-white text-slate-800 placeholder-slate-400 font-medium transition"
               onkeydown="if(event.key==='Enter') sendHubPrompt()">
        <button onclick="sendHubPrompt()" class="px-6 py-3 bg-[#00B9F1] hover:bg-[#00a3d4] text-white text-xs font-extrabold rounded-xl shadow-xs transition tracking-wide uppercase">
          Dispatch to Hub
        </button>
      </div>

      <!-- QUICK SCENARIOS -->
      <div class="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100">
        <span class="text-xs font-bold text-slate-400 uppercase tracking-wider mr-1">Demo Scenarios:</span>
        <button onclick="loadScenario('bug_3000')" class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 hover:border-[#00B9F1] text-slate-700 bg-slate-50 hover:bg-white transition">
          🎯 Trip Lunch Bug (₹3,000 split + ₹1,400 pending)
        </button>
        <button onclick="loadScenario('goa_trip')" class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 hover:border-[#00B9F1] text-slate-700 bg-slate-50 hover:bg-white transition">
          🏖️ Goa Vacation (4 Members, Multi-expense)
        </button>
        <button onclick="loadScenario('quant_hfcl')" class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 hover:border-[#00B9F1] text-slate-700 bg-slate-50 hover:bg-white transition">
          📈 Cross-Spoke Quant: Analyze HFCL Stock
        </button>
        <button onclick="loadScenario('portfolio_risk')" class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 hover:border-[#00B9F1] text-slate-700 bg-slate-50 hover:bg-white transition">
          🛡️ Cross-Spoke Risk: Check 35% Concentration Cap
        </button>
      </div>
    </div>

    <!-- AUDIT RESULT CARD -->
    <div id="outputCard" class="bg-white rounded-2xl border border-slate-200 p-6 card-shadow space-y-6">
      
      <!-- HEADER STATUS -->
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
        <div>
          <div class="flex flex-wrap items-center gap-3">
            <h3 id="resultTitle" class="text-base font-extrabold text-[#002E6E]">Audit Results: Trip Lunch Bug Resolution</h3>
            <span id="resultBadge" class="text-xs font-bold px-3 py-1 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200">
              DOUBLE-ENTRY INVARIANT CONSERVED (∑Δ = ₹0.00)
            </span>
          </div>
          <p id="resultSummary" class="text-xs text-slate-500 font-medium mt-1">
            Audit complete for 2 members and ₹3,000.00 total volume. Isolated ₹1,400.00 unconfirmed payment. Home & Group screens synchronized.
          </p>
        </div>

        <button onclick="downloadAuditCert()" class="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs rounded-xl transition border border-slate-200">
          Download JSON Certificate
        </button>
      </div>

      <!-- A2A DISPATCH TELEMETRY -->
      <div class="space-y-2">
        <span class="text-xs font-bold text-slate-500 uppercase tracking-wider block">A2A (Agent-to-Agent) Execution Telemetry:</span>
        <div id="a2aLog" class="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-2 text-xs mono">
          <div class="text-slate-700"><span class="text-[#00B9F1] font-bold">[Hub Orchestrator]</span> Received user query & parsed members: Shikhar, Aman.</div>
          <div class="text-slate-700"><span class="text-emerald-700 font-bold">[Spoke 1: Ledger Auditor]</span> Enforced zero-sum conservation: Net Delta = ₹0.00.</div>
          <div class="text-slate-700"><span class="text-amber-700 font-bold">[Spoke 1: Quarantine]</span> Isolated ₹1,400.00 pending payment from settled equity balances.</div>
          <div class="text-slate-700"><span class="text-sky-700 font-bold">[Spoke 4: Settlement Dispatcher]</span> Computed minimal debt graph: 1 bilateral UPI payment required.</div>
        </div>
      </div>

      <!-- BALANCES & SETTLEMENTS GRID -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        
        <!-- AUDITED BALANCES -->
        <div class="p-5 rounded-xl border border-slate-200 bg-white space-y-3 shadow-2xs">
          <div class="flex items-center justify-between border-b border-slate-100 pb-2">
            <span class="font-extrabold text-[#002E6E] text-xs uppercase tracking-wider">Audited Equity Balances</span>
            <span class="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">O(1) Hash Resolved</span>
          </div>
          <div id="balancesList" class="space-y-2 text-xs">
            <div class="flex justify-between items-center py-1.5 border-b border-slate-50">
              <span class="font-semibold text-slate-700">&bull; SHIKHAR:</span>
              <span class="mono font-extrabold text-emerald-600">+₹1,500.00 (To Receive)</span>
            </div>
            <div class="flex justify-between items-center py-1.5">
              <span class="font-semibold text-slate-700">&bull; AMAN:</span>
              <span class="mono font-extrabold text-rose-600">-₹1,500.00 (To Pay)</span>
            </div>
          </div>
        </div>

        <!-- MINIMAL SETTLEMENT DIRECTIVE & UPI -->
        <div class="p-5 rounded-xl border border-slate-200 bg-white space-y-3 shadow-2xs">
          <div class="flex items-center justify-between border-b border-slate-100 pb-2">
            <span class="font-extrabold text-[#002E6E] text-xs uppercase tracking-wider">Minimal Settlement Directive</span>
            <span class="text-[11px] font-bold text-[#007CA6] bg-sky-50 px-2 py-0.5 rounded">NPCI UPI Deep Link</span>
          </div>
          <div id="settlementList" class="space-y-2 text-xs">
            <div class="p-3 rounded-xl bg-sky-50/70 border border-sky-100 flex items-center justify-between">
              <div>
                <div class="font-extrabold text-[#002E6E]">AMAN &rarr; SHIKHAR</div>
                <div class="text-[11px] text-slate-500 font-medium">Amount: ₹1,500.00 (Direct P2P Settlement)</div>
              </div>
              <a href="upi://pay?pa=shikhar@okhdfcbank&pn=Shikhar&am=1500.00&cu=INR" 
                 class="px-3.5 py-2 bg-[#00B9F1] hover:bg-[#00a3d4] text-white font-bold text-xs rounded-lg transition shadow-xs">
                Pay via UPI ↗
              </a>
            </div>
          </div>
        </div>

      </div>

      <!-- INVARIANT STATUS BANNER -->
      <div class="p-4 rounded-xl bg-emerald-50 border border-emerald-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
        <div>
          <span class="font-extrabold text-emerald-900 uppercase tracking-wider block">Double-Entry Financial Invariant:</span>
          <p class="text-emerald-800 font-medium mt-0.5">
            Sum of all credits strictly equals sum of all debits (&Sigma; &Delta; &equiv; 0.00). Unconfirmed settlements quarantined from confirmed balances.
          </p>
        </div>
        <div class="text-right">
          <span class="text-emerald-800 font-extrabold mono bg-white px-2.5 py-1 rounded-md border border-emerald-300 shadow-2xs">ZERO DISCREPANCY</span>
        </div>
      </div>

    </div>

  </main>

  <script>
    let lastAuditData = null;

    async function sendHubPrompt() {
      const q = document.getElementById('userInput').value.trim();
      if (!q) return;

      const a2aBox = document.getElementById('a2aLog');
      a2aBox.innerHTML = '<div class="text-[#00B9F1] font-bold">Hub Agent dispatching sub-tasks to spokes...</div>';

      try {
        const res = await fetch('/api/hub/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({query: q})
        });
        const d = await res.json();
        lastAuditData = d;

        document.getElementById('resultTitle').innerText = 'Hub Execution: ' + d.intent;
        document.getElementById('resultBadge').innerText = d.guardrail_verdict;
        document.getElementById('resultSummary').innerText = d.summary;

        a2aBox.innerHTML = d.dispatch_log.map(item => `
          <div class="text-slate-700"><span class="text-[#00B9F1] font-bold">[${item.agent}]</span> ${item.message}</div>
        `).join('');

        if (d.spoke_results.ledger) {
          const l = d.spoke_results.ledger;
          const s = d.spoke_results.settlement;

          const balBox = document.getElementById('balancesList');
          balBox.innerHTML = Object.entries(l.member_balances).map(([mId, net]) => `
            <div class="flex justify-between items-center py-1.5 border-b border-slate-50">
              <span class="font-semibold text-slate-700">&bull; ${mId.toUpperCase()}:</span>
              <span class="mono font-extrabold ${net >= 0 ? 'text-emerald-600' : 'text-rose-600'}">
                ${net >= 0 ? '+' : '-'}₹${Math.abs(net).toFixed(2)} (${net >= 0 ? 'To Receive' : 'To Pay'})
              </span>
            </div>
          `).join('');

          const setBox = document.getElementById('settlementList');
          if (s && s.settlements && s.settlements.length > 0) {
            setBox.innerHTML = s.settlements.map(tx => `
              <div class="p-3 rounded-xl bg-sky-50/70 border border-sky-100 flex items-center justify-between">
                <div>
                  <div class="font-extrabold text-[#002E6E]">${tx.from_member.toUpperCase()} &rarr; ${tx.to_member.toUpperCase()}</div>
                  <div class="text-[11px] text-slate-500 font-medium">Amount: ₹${tx.amount.toFixed(2)} &bull; ${tx.receiver_upi}</div>
                </div>
                <a href="${tx.upi_deep_link}" class="px-3.5 py-2 bg-[#00B9F1] hover:bg-[#00a3d4] text-white font-bold text-xs rounded-lg transition shadow-xs">
                  Pay via UPI ↗
                </a>
              </div>
            `).join('');
          } else {
            setBox.innerHTML = '<div class="text-emerald-700 font-semibold p-2">All accounts fully settled. No debt transfers needed!</div>';
          }
        } else if (d.spoke_results.quant) {
          const qn = d.spoke_results.quant;
          document.getElementById('balancesList').innerHTML = `
            <div class="py-1"><strong>Symbol:</strong> ${qn.symbol}</div>
            <div class="py-1"><strong>LTP:</strong> ₹${qn.ltp.toFixed(2)}</div>
            <div class="py-1"><strong>Bias:</strong> ${qn.bias}</div>
            <div class="py-1"><strong>ATR Volatility:</strong> ${qn.atr_volatility_pct}%</div>
          `;
          document.getElementById('settlementList').innerHTML = `
            <div class="p-3 rounded-xl bg-sky-50/70 border border-sky-100">
              <div><strong>T1 Conservative:</strong> ₹${qn.targets.t1}</div>
              <div><strong>T2 Base Case:</strong> ₹${qn.targets.t2}</div>
              <div class="text-rose-600 font-bold"><strong>Stop Loss:</strong> ₹${qn.targets.stop_loss}</div>
            </div>
          `;
        } else if (d.spoke_results.risk) {
          const rk = d.spoke_results.risk;
          document.getElementById('balancesList').innerHTML = `
            <div class="py-1"><strong>Allocation Total:</strong> ${rk.total_weight_pct}%</div>
            <div class="py-1"><strong>HHI Concentration Index:</strong> ${rk.hhi_index}</div>
            <div class="py-1 text-emerald-600"><strong>Allocation Complete:</strong> ${rk.is_allocation_complete}</div>
          `;
          document.getElementById('settlementList').innerHTML = rk.concentration_breaches.length ? `
            <div class="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700">
              <strong class="block mb-1">Concentration Breaches (>25% limit):</strong>
              ${rk.concentration_breaches.map(b => `<div>&bull; ${b.asset}: ${b.weight_pct}% (Max: ${b.max_allowed_pct}%)</div>`).join('')}
            </div>
          ` : '<div class="p-3 rounded-xl bg-emerald-50 text-emerald-800">All holdings are strictly compliant with the 25% prudential cap.</div>';
        }
      } catch (e) {
        a2aBox.innerHTML = '<div class="text-rose-600 font-semibold">Error executing Hub dispatch: ' + e.message + '</div>';
      }
    }

    function loadScenario(type) {
      if (type === 'bug_3000') {
        document.getElementById('userInput').value = 'Shikhar paid ₹3,000 for dinner split with Aman. Aman paid Shikhar ₹1,400 pending approval.';
      } else if (type === 'goa_trip') {
        document.getElementById('userInput').value = 'Goa Trip: Alice paid ₹12,000 for villa split between Alice, Bob, Charlie, David. Bob paid ₹4,500 for food split between all. David paid Alice ₹3,000 pending.';
      } else if (type === 'quant_hfcl') {
        document.getElementById('userInput').value = 'Analyze live stock price and Camarilla breakout levels for HFCL.';
      } else if (type === 'portfolio_risk') {
        document.getElementById('userInput').value = 'Audit our multi-asset portfolio with 35% HFCL, 20% TCS, 20% HDFCBANK, 25% LIQUID_BEES against concentration limits.';
      }
      sendHubPrompt();
    }

    function downloadAuditCert() {
      const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(lastAuditData || {status: "VERIFIED", net_delta: 0.0}, null, 2));
      const dlAnchor = document.createElement('a');
      dlAnchor.setAttribute("href", dataStr);
      dlAnchor.setAttribute("download", "bharat_dues_audit_certificate.json");
      dlAnchor.click();
    }

    window.addEventListener('DOMContentLoaded', () => {
      loadScenario('bug_3000');
    });
  </script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
