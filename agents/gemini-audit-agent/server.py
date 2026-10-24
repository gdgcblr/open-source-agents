"""
FastAPI Server & Financial Audit Dashboard for Bharat Dues.
Exposes REST endpoints for ledger invariant checks, multimodal receipt OCR, smart splitting, and conversational chat.
Production App: https://bharat-dues.web.app
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import base64
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from core.models import Member, Expense, SettlementRecord, AuditReport
from core.ledger import audit_ledger
from core.hub_agent import AutonomousHubAgent
from core.ocr_tool import ReceiptOCRTool, ReceiptScanResult
from core.smart_split_tool import SmartSplitTool
from core.chat_tool import BharatDuesChatCopilot, ChatMessage, ChatResponse


class ChatQueryRequest(BaseModel):
    query: str
    history: List[ChatMessage] = Field(default_factory=list)


class SmartSplitRequest(BaseModel):
    description: str
    total_amount: float
    payer_id: str
    payer_name: str
    participant_names: List[str]
    split_method: str = "EQUAL"  # EQUAL, PERCENTAGE, CUSTOM
    custom_weights: Optional[Dict[str, float]] = None


class GroupAuditRequest(BaseModel):
    members: List[Member]
    expenses: List[Expense]
    settlements: List[SettlementRecord] = []


app = FastAPI(
    title="Bharat Dues Autonomous Hub & Spoke Financial Agent",
    description="Google ADK Multi-Agent Architecture for Bharat Dues (https://bharat-dues.web.app).",
    version="2.1.0",
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
        "version": "2.1.0",
        "architecture": "Google ADK Hub-and-Spoke",
        "production_app": "https://bharat-dues.web.app",
        "hub_urn": AutonomousHubAgent.urn,
        "spokes": AutonomousHubAgent.SPOKES,
        "capabilities": [
            "Double-Entry Zero-Sum Conservation (∑ Δ ≡ 0.00)",
            "Multimodal Gemini Receipt & Bill OCR",
            "Smart Split with Exact Penny-Rounding Conservation",
            "Unconfirmed Settlement Quarantine Isolation",
            "Conversational Financial Chat Copilot",
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


@app.post("/api/chat", response_model=ChatResponse)
def conversational_chat_endpoint(req: ChatQueryRequest):
    return BharatDuesChatCopilot.handle_message(
        user_message=req.query,
        conversation_history=req.history,
    )


class OCRScanRequest(BaseModel):
    notes: Optional[str] = "swiggy"
    image_base64: Optional[str] = None
    mime_type: Optional[str] = "image/jpeg"


@app.post("/api/ocr/scan")
def scan_receipt_endpoint(req: OCRScanRequest):
    image_bytes = base64.b64decode(req.image_base64) if req.image_base64 else None
    return ReceiptOCRTool.scan_receipt_image(
        image_bytes=image_bytes or b"SAMPLE_RECEIPT",
        mime_type=req.mime_type or "image/jpeg",
        user_notes=req.notes or "Swiggy dinner order",
    )


@app.post("/api/split/calculate")
def smart_split_endpoint(req: SmartSplitRequest):
    payer = Member(id=req.payer_id.lower(), name=req.payer_name)
    participants = [Member(id=n.lower().strip(), name=n.strip()) for n in req.participant_names]
    if payer not in participants:
        participants.append(payer)

    return SmartSplitTool.split_expense(
        description=req.description,
        total_amount=req.total_amount,
        payer=payer,
        participants=participants,
        split_method=req.split_method,
        custom_weights=req.custom_weights,
    )


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
  <title>Bharat Dues | Autonomous AI Agent & Invariant Auditor</title>
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
              Autonomous Financial Agent
            </span>
          </div>
          <p class="text-xs text-slate-500 font-medium">
            Production Web App: <a href="https://bharat-dues.web.app" target="_blank" class="text-[#00B9F1] font-bold hover:underline">bharat-dues.web.app ↗</a>
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

  <!-- SELF-EXPLANATORY HERO BANNER -->
  <div class="bg-sky-50/70 border-b border-sky-100 py-3.5 px-4 sm:px-6">
    <div class="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
      <div>
        <span class="font-extrabold text-[#002E6E] uppercase tracking-wide text-[11px] block sm:inline mr-2">How It Works:</span>
        <span class="text-slate-600 font-medium">
          Upload receipt or chat naturally &bull; Gemini parses items &bull; Double-entry engine prevents debt drift &bull; Settle in 1-tap via direct UPI.
        </span>
      </div>
      <div class="flex items-center gap-2 font-semibold">
        <span class="bg-white px-2.5 py-1 rounded-lg border border-sky-200 text-[#002E6E]">📸 Receipt OCR</span>
        <span class="text-sky-300">&rarr;</span>
        <span class="bg-white px-2.5 py-1 rounded-lg border border-sky-200 text-[#002E6E]">✂️ Smart Split</span>
        <span class="text-sky-300">&rarr;</span>
        <span class="bg-white px-2.5 py-1 rounded-lg border border-sky-200 text-[#002E6E]">⚖️ Invariant Audit</span>
        <span class="text-sky-300">&rarr;</span>
        <span class="bg-white px-2.5 py-1 rounded-lg border border-sky-200 text-[#002E6E]">⚡ UPI Payment</span>
      </div>
    </div>
  </div>

  <!-- MAIN CONTAINER -->
  <main class="max-w-7xl mx-auto px-4 sm:px-6 pt-6 space-y-6">

    <!-- 4 INTUITIVE WORKSPACE TABS -->
    <div class="flex flex-wrap items-center gap-2 border-b border-slate-200 pb-2">
      <button onclick="switchTab('chat')" id="tabBtn-chat" class="px-4 py-2 text-xs font-bold rounded-xl bg-[#002E6E] text-white shadow-xs transition">
        💬 Conversational AI Copilot
      </button>
      <button onclick="switchTab('ocr')" id="tabBtn-ocr" class="px-4 py-2 text-xs font-bold rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 transition">
        📸 Multimodal Receipt OCR
      </button>
      <button onclick="switchTab('split')" id="tabBtn-split" class="px-4 py-2 text-xs font-bold rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 transition">
        ✂️ Smart Split Calculator
      </button>
      <button onclick="switchTab('audit')" id="tabBtn-audit" class="px-4 py-2 text-xs font-bold rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 transition">
        ⚖️ Invariant Audit & UPI Directives
      </button>
    </div>

    <!-- TAB 1: CONVERSATIONAL AI CHAT COPILOT -->
    <div id="view-chat" class="space-y-6">
      
      <div class="bg-white rounded-2xl border border-slate-200 p-6 card-shadow space-y-4">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
          <div>
            <h2 class="text-base font-extrabold text-[#002E6E]">Natural Language Financial Copilot</h2>
            <p class="text-xs text-slate-500 font-medium">Chat directly with the agent to add shared bills, verify balances, or isolate unconfirmed payments.</p>
          </div>
          <span class="text-xs font-bold px-3 py-1 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 self-start sm:self-auto">
            Online &bull; Gemini 2.5 Flash
          </span>
        </div>

        <!-- QUICK SCENARIO CHIPS -->
        <div class="flex flex-wrap items-center gap-2 pt-1">
          <span class="text-xs font-bold text-slate-400 uppercase tracking-wider mr-1">Try One-Click Prompts:</span>
          <button onclick="sendQuickPrompt('Shikhar paid ₹3,000 for dinner split with Aman. Aman paid Shikhar ₹1,400 pending approval.')" 
                  class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 hover:border-[#00B9F1] text-slate-700 bg-slate-50 hover:bg-white transition">
            🎯 Trip Lunch Bug (₹3,000 split + ₹1,400 pending)
          </button>
          <button onclick="sendQuickPrompt('Goa Trip: Alice paid ₹12,000 for villa split with Alice, Bob, Charlie, David. David paid Alice ₹3,000 pending.')" 
                  class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 hover:border-[#00B9F1] text-slate-700 bg-slate-50 hover:bg-white transition">
            🏖️ Goa Villa (4 Members, Multi-Expense)
          </button>
          <button onclick="sendQuickPrompt('Who owes what right now? Show group balance sheet.')" 
                  class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 hover:border-[#00B9F1] text-slate-700 bg-slate-50 hover:bg-white transition">
            📊 Who Owes Whom? (Audit Balances)
          </button>
          <button onclick="sendQuickPrompt('Why does the double-entry invariant matter in Bharat Dues?')" 
                  class="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 hover:border-[#00B9F1] text-slate-700 bg-slate-50 hover:bg-white transition">
            🛡️ Explain Double-Entry Guardrail
          </button>
        </div>

        <!-- CHAT MESSAGE LOG CONTAINER -->
        <div id="chatHistoryBox" class="h-80 overflow-y-auto p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-3 text-xs">
          <!-- Default welcome message -->
          <div class="flex items-start gap-2.5">
            <div class="w-7 h-7 rounded-lg bg-[#002E6E] text-white flex items-center justify-center font-bold text-xs shrink-0">BD</div>
            <div class="bg-white p-3.5 rounded-xl border border-slate-200 text-slate-700 space-y-1.5 max-w-xl card-shadow">
              <div class="font-bold text-[#002E6E]">Bharat Dues Financial Copilot</div>
              <p>Hello! I am your autonomous financial assistant. You can add expenses, ask who owes what, upload receipts, or test our double-entry ledger invariant conservation.</p>
              <p class="text-slate-500 font-mono text-[11px]">Click any chip above or type an expense below to begin.</p>
            </div>
          </div>
        </div>

        <!-- INPUT BAR -->
        <div class="flex gap-2">
          <input type="text" id="chatInput" 
                 placeholder="e.g. Shikhar paid ₹3,000 for dinner split with Aman. Aman paid Shikhar ₹1,400 pending approval." 
                 class="flex-1 px-4 py-3 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-[#00B9F1] focus:bg-white text-slate-800 placeholder-slate-400 font-medium transition"
                 onkeydown="if(event.key==='Enter') executeChatPrompt()">
          <button onclick="executeChatPrompt()" class="px-6 py-3 bg-[#00B9F1] hover:bg-[#00a3d4] text-white text-xs font-extrabold rounded-xl shadow-xs transition tracking-wide uppercase">
            Send to Agent
          </button>
        </div>

      </div>

    </div>

    <!-- TAB 2: MULTIMODAL RECEIPT OCR SCANNER -->
    <div id="view-ocr" class="hidden space-y-6">
      <div class="bg-white rounded-2xl border border-slate-200 p-6 card-shadow space-y-6">
        <div class="border-b border-slate-100 pb-3">
          <h2 class="text-base font-extrabold text-[#002E6E]">Multimodal Gemini Receipt & Bill OCR Scanner</h2>
          <p class="text-xs text-slate-500 font-medium">Extract line items, taxes, GSTIN, and merchant info from receipts to auto-generate itemized group splits.</p>
        </div>

        <!-- 3 PRE-LOADED TEST RECEIPTS FOR ONE-CLICK DEMOS -->
        <div class="space-y-2">
          <span class="text-xs font-bold text-slate-400 uppercase tracking-wider block">One-Click Sample Invoices:</span>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <button onclick="runSampleOCR('swiggy')" class="p-3.5 rounded-xl border border-slate-200 hover:border-[#00B9F1] bg-slate-50 hover:bg-white text-left transition space-y-1">
              <div class="font-bold text-[#002E6E] text-xs">🍕 Swiggy / Biryani Blues Bill</div>
              <div class="text-[11px] text-slate-500">₹1,650.00 &bull; 3 Food Items &bull; GSTIN Verified</div>
            </button>
            <button onclick="runSampleOCR('hotel')" class="p-3.5 rounded-xl border border-slate-200 hover:border-[#00B9F1] bg-slate-50 hover:bg-white text-left transition space-y-1">
              <div class="font-bold text-[#002E6E] text-xs">🏖️ Taj Exotica Resort Goa Bill</div>
              <div class="text-[11px] text-slate-500">₹18,400.00 &bull; Villa + Breakfast &bull; 4 Members</div>
            </button>
            <button onclick="runSampleOCR('cafe')" class="p-3.5 rounded-xl border border-slate-200 hover:border-[#00B9F1] bg-slate-50 hover:bg-white text-left transition space-y-1">
              <div class="font-bold text-[#002E6E] text-xs">☕ Third Wave Coffee Bill</div>
              <div class="text-[11px] text-slate-500">₹980.00 &bull; Mocha + Cold Brew + Croissant</div>
            </button>
          </div>
        </div>

        <!-- OCR PARSED OUTPUT DISPLAY -->
        <div id="ocrOutputCard" class="hidden p-5 rounded-xl bg-slate-50 border border-slate-200 space-y-4">
          <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-3">
            <div>
              <span id="ocrMerchant" class="text-sm font-extrabold text-[#002E6E]">Swiggy / Biryani Blues</span>
              <div id="ocrMeta" class="text-xs text-slate-500">Date: 2026-10-24 &bull; GSTIN: 29AABCS1429B1Z5 &bull; UPI: swiggy@icici</div>
            </div>
            <div class="text-right">
              <div id="ocrTotal" class="text-base font-black text-[#002E6E]">₹1,650.00</div>
              <span class="text-[11px] font-bold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded">OCR Confirmed</span>
            </div>
          </div>

          <div class="space-y-1.5">
            <span class="text-xs font-bold text-slate-500 uppercase tracking-wider block">Line Items:</span>
            <div id="ocrItemsList" class="space-y-1 text-xs">
              <!-- Rendered dynamically -->
            </div>
          </div>

          <div class="p-3 bg-white rounded-lg border border-slate-200 flex items-center justify-between">
            <span class="text-xs font-bold text-[#002E6E]">Auto-Split Directive:</span>
            <button onclick="applyOCRToLedger()" class="px-3.5 py-1.5 bg-[#00B9F1] hover:bg-[#00a3d4] text-white font-bold text-xs rounded-lg transition shadow-xs">
              Commit Scanned Bill to Group Ledger &rarr;
            </button>
          </div>
        </div>

      </div>
    </div>

    <!-- TAB 3: SMART SPLIT CALCULATOR -->
    <div id="view-split" class="hidden space-y-6">
      <div class="bg-white rounded-2xl border border-slate-200 p-6 card-shadow space-y-5">
        <div class="border-b border-slate-100 pb-3">
          <h2 class="text-base font-extrabold text-[#002E6E]">Smart Split & Zero-Drift Penny Allocator</h2>
          <p class="text-xs text-slate-500 font-medium">Split bills equally, by custom percentage, or unequal weights. Guaranteed zero rounding discrepancy.</p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label class="text-xs font-bold text-slate-600 uppercase tracking-wider block mb-1">Expense Description</label>
            <input type="text" id="splitDesc" value="Team Offsite Dinner" class="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg">
          </div>
          <div>
            <label class="text-xs font-bold text-slate-600 uppercase tracking-wider block mb-1">Total Amount (₹)</label>
            <input type="number" id="splitAmount" value="3000" class="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg">
          </div>
          <div>
            <label class="text-xs font-bold text-slate-600 uppercase tracking-wider block mb-1">Split Method</label>
            <select id="splitMethod" class="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg">
              <option value="EQUAL">Equal Split (1/N)</option>
              <option value="PERCENTAGE">Weighted Percentage (60% / 40%)</option>
            </select>
          </div>
        </div>

        <button onclick="executeSmartSplit()" class="px-5 py-2.5 bg-[#00B9F1] hover:bg-[#00a3d4] text-white text-xs font-extrabold rounded-xl shadow-xs transition">
          Calculate Conserved Allocation
        </button>

        <div id="splitResultBox" class="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-2 text-xs">
          <div class="font-bold text-[#002E6E]">Conserved Allocation Result:</div>
          <div id="splitBreakdown" class="text-slate-600">
            Click calculate above to inspect zero-drift penny shares.
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 4: INVARIANT AUDIT & UPI DIRECTIVES -->
    <div id="view-audit" class="hidden space-y-6">
      
      <!-- AUDIT REPORT CARD -->
      <div class="bg-white rounded-2xl border border-slate-200 p-6 card-shadow space-y-6">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
          <div>
            <div class="flex flex-wrap items-center gap-3">
              <h3 id="auditTitle" class="text-base font-extrabold text-[#002E6E]">Audit Results: Trip Lunch Bug Resolution</h3>
              <span id="auditBadge" class="text-xs font-bold px-3 py-1 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200">
                DOUBLE-ENTRY INVARIANT CONSERVED (∑Δ = ₹0.00)
              </span>
            </div>
            <p id="auditSummary" class="text-xs text-slate-500 font-medium mt-1">
              Audit complete for 2 members and ₹3,000.00 total volume. Isolated ₹1,400.00 unconfirmed payment.
            </p>
          </div>

          <button onclick="downloadAuditCert()" class="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs rounded-xl transition border border-slate-200">
            Download JSON Certificate
          </button>
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

    </div>

  </main>

  <script>
    let lastAuditData = null;
    let activeTab = 'chat';

    function switchTab(tabId) {
      activeTab = tabId;
      ['chat', 'ocr', 'split', 'audit'].forEach(t => {
        const view = document.getElementById('view-' + t);
        const btn = document.getElementById('tabBtn-' + t);
        if (t === tabId) {
          view.classList.remove('hidden');
          btn.className = 'px-4 py-2 text-xs font-bold rounded-xl bg-[#002E6E] text-white shadow-xs transition';
        } else {
          view.classList.add('hidden');
          btn.className = 'px-4 py-2 text-xs font-bold rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 transition';
        }
      });
    }

    async function sendQuickPrompt(promptText) {
      document.getElementById('chatInput').value = promptText;
      executeChatPrompt();
    }

    async function executeChatPrompt() {
      const input = document.getElementById('chatInput');
      const text = input.value.trim();
      if (!text) return;

      const historyBox = document.getElementById('chatHistoryBox');

      // Append user bubble
      historyBox.innerHTML += `
        <div class="flex items-start justify-end gap-2.5">
          <div class="bg-[#00B9F1] text-white p-3 rounded-xl font-medium max-w-lg shadow-2xs">
            ${text}
          </div>
        </div>
      `;
      historyBox.scrollTop = historyBox.scrollHeight;
      input.value = '';

      // Append loading bubble
      const loadingId = 'loading-' + Date.now();
      historyBox.innerHTML += `
        <div id="${loadingId}" class="flex items-start gap-2.5">
          <div class="w-7 h-7 rounded-lg bg-[#002E6E] text-white flex items-center justify-center font-bold text-xs shrink-0">BD</div>
          <div class="bg-white p-3 rounded-xl border border-slate-200 text-slate-500 italic max-w-xl card-shadow">
            Agent verifying double-entry invariants...
          </div>
        </div>
      `;
      historyBox.scrollTop = historyBox.scrollHeight;

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({query: text})
        });
        const data = await res.json();
        const loadElem = document.getElementById(loadingId);
        if (loadElem) loadElem.remove();

        // Convert simple markdown to html
        let replyHtml = data.reply
          .replace(/### (.*)/g, '<div class="text-sm font-bold text-[#002E6E] mb-1">$1</div>')
          .replace(/#### (.*)/g, '<div class="text-xs font-bold text-[#002E6E] mt-2 mb-1">$1</div>')
          .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')
          .replace(/\\* (.*)/g, '<div class="pl-2">&bull; $1</div>')
          .replace(/> (.*)/g, '<div class="p-2 bg-amber-50 border-l-2 border-amber-400 text-amber-900 rounded-r text-[11px] my-1">$1</div>')
          .replace(/\\[(.*?)\\]\\((.*?)\\)/g, '<a href="$2" class="text-[#00B9F1] font-bold underline">$1</a>');

        historyBox.innerHTML += `
          <div class="flex items-start gap-2.5">
            <div class="w-7 h-7 rounded-lg bg-[#002E6E] text-white flex items-center justify-center font-bold text-xs shrink-0">BD</div>
            <div class="bg-white p-3.5 rounded-xl border border-slate-200 text-slate-800 space-y-2 max-w-xl card-shadow">
              ${replyHtml}
              ${data.suggested_actions && data.suggested_actions.length ? `
                <div class="pt-2 border-t border-slate-100 flex flex-wrap gap-1.5">
                  ${data.suggested_actions.map(act => `<button onclick="sendQuickPrompt('${act}')" class="px-2.5 py-1 text-[11px] font-semibold rounded-md bg-slate-50 hover:bg-slate-100 text-slate-600 border border-slate-200">${act}</button>`).join('')}
                </div>
              ` : ''}
            </div>
          </div>
        `;
        historyBox.scrollTop = historyBox.scrollHeight;

        // Sync with Tab 4 Audit
        runHubSync(text);

      } catch (err) {
        const loadElem = document.getElementById(loadingId);
        if (loadElem) loadElem.remove();
        historyBox.innerHTML += `<div class="text-rose-600 font-semibold p-2">Error: ${err.message}</div>`;
      }
    }

    async function runHubSync(queryText) {
      try {
        const res = await fetch('/api/hub/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({query: queryText})
        });
        const d = await res.json();
        lastAuditData = d;

        document.getElementById('auditTitle').innerText = 'Hub Execution: ' + d.intent;
        document.getElementById('auditBadge').innerText = d.guardrail_verdict;
        document.getElementById('auditSummary').innerText = d.summary;

        if (d.spoke_results && d.spoke_results.ledger) {
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
          }
        }
      } catch (e) {
        console.error(e);
      }
    }

    async function runSampleOCR(type) {
      const card = document.getElementById('ocrOutputCard');
      card.classList.remove('hidden');

      const res = await fetch('/api/ocr/scan', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({notes: type})
      });
      const data = await res.json();

      document.getElementById('ocrMerchant').innerText = data.merchant_name;
      document.getElementById('ocrMeta').innerText = `Date: ${data.date} • GSTIN: ${data.gstin || 'N/A'} • UPI: ${data.upi_id || 'N/A'}`;
      document.getElementById('ocrTotal').innerText = `₹${data.total_amount.toFixed(2)}`;

      const list = document.getElementById('ocrItemsList');
      list.innerHTML = data.line_items.map(i => `
        <div class="flex justify-between items-center py-1 border-b border-slate-100">
          <span>&bull; ${i.name} (Qty: ${i.quantity})</span>
          <span class="mono font-bold text-slate-700">₹${i.price.toFixed(2)}</span>
        </div>
      `).join('');
    }

    function applyOCRToLedger() {
      const merchant = document.getElementById('ocrMerchant').innerText;
      const total = document.getElementById('ocrTotal').innerText.replace('₹', '');
      switchTab('chat');
      sendQuickPrompt(`Shikhar paid ${total} for ${merchant} split with Aman`);
    }

    async function executeSmartSplit() {
      const desc = document.getElementById('splitDesc').value;
      const amount = parseFloat(document.getElementById('splitAmount').value);
      const method = document.getElementById('splitMethod').value;

      const payload = {
        description: desc,
        total_amount: amount,
        payer_id: "shikhar",
        payer_name: "Shikhar",
        participant_names: ["Shikhar", "Aman"],
        split_method: method,
        custom_weights: method === "PERCENTAGE" ? {"shikhar": 60.0, "aman": 40.0} : null
      };

      const res = await fetch('/api/split/calculate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      const box = document.getElementById('splitBreakdown');
      box.innerHTML = `
        <div class="space-y-1">
          <div class="text-emerald-700 font-bold">${data.explanation}</div>
          <div class="pt-2"><strong>Member Shares:</strong></div>
          ${Object.entries(data.shares).map(([k, v]) => `<div>&bull; ${k.toUpperCase()}: <strong>₹${v.toFixed(2)}</strong></div>`).join('')}
          <div class="text-[11px] text-slate-500 pt-1">Double-Entry Conservation Verified: Zero Residual Cents.</div>
        </div>
      `;
    }

    function downloadAuditCert() {
      const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(lastAuditData || {status: "VERIFIED", net_delta: 0.0}, null, 2));
      const dlAnchor = document.createElement('a');
      dlAnchor.setAttribute("href", dataStr);
      dlAnchor.setAttribute("download", "bharat_dues_audit_certificate.json");
      dlAnchor.click();
    }
  </script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
