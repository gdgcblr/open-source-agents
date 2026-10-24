"""FastAPI REST API Server & Embedded Visual Dashboard for Gemini Audit Agent."""
from __future__ import annotations
import os
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from core.models import Member, Expense, SettlementRecord, AuditReport
from core.ledger import audit_ledger
from core.gemini_parser import parse_unstructured_ledger

load_dotenv()

app = FastAPI(
    title="Gemini Audit Agent API",
    description="Autonomous Double-Entry Accounting & Ledger Invariant Audit Engine",
    version="1.0.0",
)


class TextAuditRequest(BaseModel):
    text: str


class StructuredAuditRequest(BaseModel):
    members: List[Member]
    expenses: List[Expense]
    settlements: Optional[List[SettlementRecord]] = []


@app.get("/healthz", tags=["Health"])
def healthcheck():
    """Health check endpoint for Docker container orchestrators and automated tests."""
    return {"status": "ok", "service": "gemini-audit-agent", "version": "1.0.0"}


@app.post("/api/audit/text", response_model=AuditReport, tags=["Audit"])
def audit_text_endpoint(req: TextAuditRequest):
    """Parses raw text (receipts, chat notes) via Gemini/Heuristics and audits ledger invariants."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")
    members, expenses, settlements = parse_unstructured_ledger(req.text)
    if not expenses and not settlements:
        raise HTTPException(status_code=422, detail="No expenses or settlements could be extracted from input.")
    return audit_ledger(members, expenses, settlements)


@app.post("/api/audit/structured", response_model=AuditReport, tags=["Audit"])
def audit_structured_endpoint(req: StructuredAuditRequest):
    """Audits a structured ledger with members, expenses, and settlements."""
    return audit_ledger(req.members, req.expenses, req.settlements or [])


@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
def web_dashboard():
    """Embedded interactive visual dashboard for DevFest judges and reviewers."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Gemini Audit Agent · DevFest Open Source</title>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --primary-blue: #00B9F1;
      --dark-blue: #002E6E;
      --bg-color: #F4F7FB;
      --surface: #FFFFFF;
      --text: #0F172A;
      --text-muted: #64748B;
      --green: #10B981;
      --red: #EF4444;
      --amber: #F59E0B;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Outfit', sans-serif;
      background: var(--bg-color);
      color: var(--text);
      padding: 32px 20px;
    }
    .container { max-width: 900px; margin: 0 auto; }
    header {
      background: linear-gradient(135deg, var(--dark-blue) 0%, #001A40 100%);
      color: white;
      padding: 32px;
      border-radius: 20px;
      margin-bottom: 24px;
      box-shadow: 0 10px 25px rgba(0,46,110,0.15);
    }
    .badge {
      display: inline-block;
      background: rgba(0,185,241,0.2);
      color: var(--primary-blue);
      padding: 4px 12px;
      border-radius: 99px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1px;
      text-transform: uppercase;
      margin-bottom: 12px;
    }
    h1 { font-size: 28px; font-weight: 800; margin-bottom: 8px; }
    p.subtitle { color: rgba(255,255,255,0.7); font-size: 14px; }
    .card {
      background: var(--surface);
      border-radius: 16px;
      padding: 24px;
      margin-bottom: 20px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.04);
      border: 1px solid rgba(0,0,0,0.06);
    }
    textarea {
      width: 100%;
      height: 100px;
      border: 1.5px solid #E2E8F0;
      border-radius: 12px;
      padding: 14px;
      font-family: inherit;
      font-size: 14px;
      resize: vertical;
      margin-bottom: 16px;
      outline: none;
    }
    textarea:focus { border-color: var(--primary-blue); }
    button {
      background: var(--dark-blue);
      color: white;
      border: none;
      padding: 12px 24px;
      border-radius: 12px;
      font-weight: 700;
      font-size: 14px;
      cursor: pointer;
      transition: all 0.2s;
    }
    button:hover { background: #001F4D; transform: translateY(-1px); }
    .btn-secondary {
      background: #E2E8F0;
      color: var(--text);
      margin-left: 10px;
    }
    .btn-secondary:hover { background: #CBD5E1; }
    .results { display: none; margin-top: 24px; }
    .status-pill {
      display: inline-block;
      padding: 6px 14px;
      border-radius: 99px;
      font-size: 12px;
      font-weight: 800;
    }
    .pill-green { background: rgba(16,185,129,0.12); color: var(--green); }
    .pill-red { background: rgba(239,68,68,0.12); color: var(--red); }
    table { width: 100%; border-collapse: collapse; margin-top: 14px; }
    th, td { text-align: left; padding: 12px; border-bottom: 1px solid #F1F5F9; font-size: 14px; }
    th { color: var(--text-muted); font-size: 11px; text-transform: uppercase; font-weight: 700; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <span class="badge">GDG Cloud Bengaluru · DevFest 2026</span>
      <h1>Gemini Audit Agent</h1>
      <p class="subtitle">Autonomous Double-Entry Accounting & Financial Invariant Engine</p>
    </header>

    <div class="card">
      <h3 style="margin-bottom: 12px; font-weight: 700;">Audit Unstructured Ledger or Receipt Text</h3>
      <textarea id="inputText">Dinner of 3000 paid by Alice split with Bob.
Bob paid Alice 1400 pending confirmation.</textarea>
      <div>
        <button onclick="runAudit()">🔍 Audit Financial Invariants</button>
        <button class="btn-secondary" onclick="loadDiscrepancyDemo()">Load Bug Reproduction</button>
      </div>
      <div id="results" class="results">
        <hr style="margin: 20px 0; border: none; border-top: 1px solid #F1F5F9;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
          <div>
            <span id="statusPill" class="status-pill pill-green">BALANCED (∑ ≡ 0.00)</span>
            <span id="totalSpent" style="margin-left: 12px; font-weight: 700; color: var(--text);"></span>
          </div>
          <span style="font-size: 12px; color: var(--text-muted);" id="zeroDelta"></span>
        </div>
        <h4 style="font-size: 14px; margin-top: 16px;">Member Balances</h4>
        <table id="balancesTable">
          <thead><tr><th>Member</th><th style="text-align: right;">Net Balance</th><th style="text-align: right;">Position</th></tr></thead>
          <tbody></tbody>
        </table>
        <h4 style="font-size: 14px; margin-top: 24px;">Optimal Settlement Path</h4>
        <table id="settlementsTable">
          <thead><tr><th>From</th><th>Amount</th><th>To</th><th>Payment Method</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    function loadDiscrepancyDemo() {
      document.getElementById('inputText').value = 
`Transaction of 3000 paid by Alice split with Bob.
Bob paid Alice 1400 pending.`;
      runAudit();
    }

    async function runAudit() {
      const text = document.getElementById('inputText').value;
      try {
        const res = await fetch('/api/audit/text', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({text: text})
        });
        const data = await res.json();
        
        document.getElementById('results').style.display = 'block';
        document.getElementById('totalSpent').innerText = `Total Volume: ₹${data.total_spent.toFixed(2)}`;
        document.getElementById('zeroDelta').innerText = `Conservation Delta: ₹${data.net_zero_delta.toFixed(4)}`;
        
        const pill = document.getElementById('statusPill');
        if (data.is_balanced) {
          pill.className = 'status-pill pill-green';
          pill.innerText = 'BALANCED (∑ ≡ 0.00)';
        } else {
          pill.className = 'status-pill pill-red';
          pill.innerText = 'DISCREPANCY DETECTED';
        }

        const balBody = document.querySelector('#balancesTable tbody');
        balBody.innerHTML = '';
        for (const [m, bal] of Object.entries(data.member_balances)) {
          const isCreditor = bal > 0.005;
          const isDebtor = bal < -0.005;
          const pos = isCreditor ? '<span style="color: var(--green); font-weight: 700;">Creditor (Gets Back)</span>' : (isDebtor ? '<span style="color: var(--red); font-weight: 700;">Debtor (Owes)</span>' : '<span style="color: var(--text-muted);">Settled</span>');
          const balStr = (bal >= 0 ? '+' : '') + `₹${bal.toFixed(2)}`;
          balBody.innerHTML += `<tr><td><strong>${m}</strong></td><td style="text-align: right; font-weight: 800; color: ${isCreditor ? 'var(--green)' : (isDebtor ? 'var(--red)' : 'var(--text)')};">${balStr}</td><td style="text-align: right;">${pos}</td></tr>`;
        }

        const setBody = document.querySelector('#settlementsTable tbody');
        setBody.innerHTML = '';
        if (data.optimal_settlements.length === 0) {
          setBody.innerHTML = '<tr><td colspan="4" style="color: var(--green); font-weight: 600;">All debts settled. Zero transactions required.</td></tr>';
        } else {
          for (const s of data.optimal_settlements) {
            setBody.innerHTML += `<tr><td style="color: var(--red); font-weight: 700;">${s.from_name}</td><td style="font-weight: 800;">₹${s.amount.toFixed(2)}</td><td style="color: var(--green); font-weight: 700;">${s.to_name}</td><td><span style="background: rgba(0,185,241,0.15); color: var(--dark-blue); padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 700;">UPI</span></td></tr>`;
          }
        }
      } catch (err) {
        alert('Audit execution error: ' + err.message);
      }
    }
  </script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
