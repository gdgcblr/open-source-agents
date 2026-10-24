# Master Engineering Context & Decision Log: Bharat Dues AI & Arthaniti Quant Hub

> **Target Audience / Agent:** Gemma4 in Codex (or any incoming AI pair programmer in a fresh chat session).  
> **Repository:** `open-source-agents` (`https://github.com/shikharagrawal17/open-source-agents`, Branch: `feat/gemini-audit-agent`)  
> **Context Date / Event:** Road to DevFest 2026: Open Source Edition | GDG Cloud Bengaluru at Google Ananta, Bengaluru (Oct 24, 2026).  
> **Author:** Shikhar Agrawal ([@shikharagrawal17](https://github.com/shikharagrawal17))  
> **Companion Production Web Application:** [https://bharat-dues.web.app](https://bharat-dues.web.app)

---

## 1. Executive Summary & Core Architectural Directives

This monorepo was created to demonstrate production-grade Google AI Agents using the **Google Agent Development Kit (ADK) Hub-and-Spoke Pattern**, **Model Context Protocol (MCP)**, **Google Gemini 2.5 & Gemma 2 LLMs**, and **mathematically audited financial invariant guardrails**.

### ⚠️ Critical Rule: Strict Project Separation (Never Mash Them Together)
In previous prototypes, bill-splitting logic and stock-market quant analytics were conflated into a single messy interface. We established a **strict separation of concerns**:

1. **Bharat Dues AI Audit Agent (`agents/gemini-audit-agent/`, Port 8000)**:
   - **Domain:** Group bill splitting, multimodal receipt OCR, double-entry mathematical auditing ($\sum \Delta \equiv 0.00$), and 1-tap NPCI UPI settlements.
   - **Theme:** Material 3 Light Theme matching production `https://bharat-dues.web.app` (Zero dark glassmorphism).
   - **Hub URN:** `urn:adk:hub:bharat-dues-master`
2. **Arthaniti Quant Hub & MCP (`tools/gemma-quant-mcp/`, Port 8002)**:
   - **Domain:** NSE/BSE stock quotes, certified Camarilla & Classic floor pivot matrices, SEBI-inspired portfolio risk guardrails ($\le 25\%$ concentration cap), and institutional Gemma-2 equity thesis synthesis.
   - **Theme:** Professional institutional dark/slate financial terminal.
   - **Hub URN:** `urn:adk:hub:arthaniti-quant-master`
   - **Protocol:** Model Context Protocol (MCP JSON-RPC 2.0) and REST API.

---

## 2. Project 1: Bharat Dues AI Audit Agent (Deep Dive)

### 2.1 Problem & Motivation
In decentralized shared expenses (roommates, trips, dinner bills):
- LLMs routinely hallucinate split math and drop pennies, violating $\sum \text{balances} \equiv 0.00$.
- Participant identities are fragmented across Firebase UIDs, phone numbers, and informal nicknames.
- Unconfirmed "pending" settlements pollute active balances, causing interpersonal disputes.

### 2.2 What Was Built & Implemented
1. **Google ADK Hub-and-Spoke Architecture (`core/hub_agent.py`)**:
   - `urn:adk:hub:bharat-dues-master` orchestrates 4 specialized spokes:
     - **Spoke 1: Double-Entry Ledger Auditor (`core/ledger.py`, `core/models.py`)**: Proves net zero-sum balance invariance $\sum_{m \in M} \text{NetBalance}(m) \equiv 0.00$. Isolates unverified pending payments.
     - **Spoke 2: Multimodal Receipt OCR Auditor (`core/ocr_tool.py`)**: Accepts uploaded receipt images (JPEG/PNG/WebP) via base64 or runs pre-loaded authentic templates (Swiggy, Hotel Taj Goa, Third Wave Coffee). Extracts vendor, date, line items, taxes, and total.
     - **Spoke 3: Smart Split & Penny Allocation Engine (`core/smart_split_tool.py`)**: Computes exact penny distribution ($\sum \text{shares} \equiv \text{total}$) across equal, percentage, or custom amounts. Automatically allocates remaining penny drifts to the primary payer.
     - **Spoke 4: Settlement Execution & UPI Dispatcher (`core/ledger.py`)**: Computes greedy minimal-debt graph settlement paths and generates 1-tap NPCI UPI deep links (`upi://pay?pa=...&pn=...&am=...&cu=INR`).
2. **Conversational AI Copilot (`core/chat_tool.py`, `/api/chat`)**:
   - Natural language assistant that parses unstructured expense declarations, answers balance sheet queries, and explains invariant math.
3. **Material 3 Light Web UI (`server.py`, Port 8000)**:
   - Built to mirror production [bharat-dues.web.app](https://bharat-dues.web.app).
   - High-contrast, accessibility-compliant `#002E6E` Navy and `#00B9F1` Cyan palette.
   - 4 Interactive Workspace Tabs:
     1. **AI Chat Copilot**: Interactive query box with quick-prompt chips.
     2. **Smart Receipt OCR**: Drag-and-drop file upload zone, live thumbnail preview, line-item itemization table, "Send to Splitter", and "Direct to Ledger".
     3. **Smart Split Calculator**: Dynamic member addition/removal, live percentage sliders, custom rupee amounts, auto-balance remainder button, and real-time total meter.
     4. **Double-Entry Audit**: Visual balance sheet, anomaly warnings, minimal settlement transactions, NPCI UPI buttons, and downloadable JSON Audit Certificate.
4. **Interactive In-Browser API Key Modal & Model Selector**:
   - Header button **"🔑 Configure API Key"** opens a modal to enter a Google AI Studio key.
   - Persisted in browser `localStorage` (`bharat_dues_gemini_api_key`) and sent with requests.
   - Dynamic Model Selector dropdown (`gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-1.5-flash`, `gemma-2-9b-it`).
5. **Zero-Key Resilient Fallback**:
   - If no API key is provided, the agent runs in **Deterministic Heuristic Mode** ($0.00 cost, offline-ready). Live stage demos never break.

### 2.3 Sources & References
- Live Production App: [https://bharat-dues.web.app](https://bharat-dues.web.app)
- NPCI Unified Payments Interface (UPI) Linking Specification: `upi://pay?pa={vpa}&pn={name}&am={amount}&cu=INR`
- Mathematical Invariant: Luca Pacioli Double-Entry Accounting Conservation Law ($\sum \text{Debits} \equiv \sum \text{Credits}$)

---

## 3. Project 2: Arthaniti Quant Hub & MCP Engine (Deep Dive)

### 3.1 Problem & Motivation
Financial AI agents frequently hallucinate stock price targets, recommend arbitrary stop-losses, and violate regulatory diversification guidelines.

### 3.2 What Was Built & Implemented
1. **Google ADK Hub-and-Spoke Architecture (`core/hub_agent.py`, Port 8002)**:
   - Central Orchestrator: `urn:adk:hub:arthaniti-quant-master`.
   - **Spoke 1: Realtime Market Feed & Symbol Resolver (`core/spokes/spoke_market_feed.py`, `core/market_feed.py`, `core/symbol_resolver.py`)**: Live quotes with fallback tick generation and smart ticker resolution.
   - **Spoke 2: Camarilla & Classic Pivot Engine (`core/spokes/spoke_quant_engine.py`, `core/quant_engine.py`)**: Computes exact Camarilla equilibrium levels ($H_4, H_3, L_3, L_4$), floor pivots ($P, R_1-R_3, S_1-S_3$), ATR day volatility %, and Fibonacci 1.618 extensions in $<10\text{ms}$.
   - **Spoke 3: Prudential Risk Guardrail (`core/spokes/spoke_risk_guardrail.py`, `core/invariant_guardrails.py`)**: Audits portfolio allocations against SEBI prudential concentration limits ($\le 25.0\%$ single-stock cap) and $100.00\%$ capital completeness with IEEE 754 precision protection.
   - **Spoke 4: Gemma Institutional Thesis Generator (`core/spokes/spoke_gemma_advisor.py`, `core/gemma_advisor.py`)**: Synthesizes deterministic quant bounds into structured institutional theses using Google Gemma-2-9B or Gemini 2.5 Flash.
   - **Spoke 5: Quantitative Equity Screener (`core/spokes/spoke_screener.py`, `core/screener_engine.py`)**: Scans market universe for volume breakouts and undervalued quality setups.
2. **Model Context Protocol (MCP) Server (`mcp_server.py`, `main.py mcp`)**:
   - Exposes tools via standard JSON-RPC 2.0 stdio:
     - `calculate_quant_targets`: Deterministic Camarilla & Classic pivot matrices.
     - `audit_invariants`: Double-entry zero-sum check and concentration guardrails.
     - `screen_stocks`: Momentum breakout and fundamental screeners.
     - `generate_gemma_thesis`: Institutional thesis generation.
3. **Web Terminal UI & Telemetry (`server.py`, Port 8002)**:
   - Live A2A (Agent-to-Agent) Execution Telemetry showing step-by-step task routing, latency in ms, and guardrail verification status.
   - Model Selector and API Key modal with `localStorage` persistence (`arthaniti_gemini_api_key`).
   - Fixed `loadStock` reference to `loadTicker(sym)`.

### 3.3 Sources & References
- Nick Stott Camarilla Pivot Equation:
  $$H_4 = C + (H - L) \times 1.1 / 2, \quad H_3 = C + (H - L) \times 1.1 / 4$$
  $$L_3 = C - (H - L) \times 1.1 / 4, \quad L_4 = C - (H - L) \times 1.1 / 2$$
- SEBI Mutual Fund & Portfolio Manager Regulations: Max 25% exposure per individual equity asset.
- Anthropic Model Context Protocol (MCP) Specification.

---

## 4. Google Gemini & Gemma Model Matrix

### Active & Supported Models (2025 / 2026)
| Model Identifier | Provider / Family | Status | Primary Purpose in this Repo |
| :--- | :--- | :--- | :--- |
| **`gemini-2.5-flash`** | Google Gemini 2.5 | **Active (Default Recommended)** | Realtime multimodal receipt OCR, low-latency conversational copilot, fast equity thesis synthesis |
| **`gemini-2.5-pro`** | Google Gemini 2.5 | **Active** | Complex multi-party dispute resolution, deep financial reasoning |
| **`gemini-2.5-flash-lite`**| Google Gemini 2.5 | **Active** | Ultra low-latency, high-throughput extraction |
| **`gemini-1.5-flash`** | Google Gemini 1.5 (LTS) | **Active (LTS)** | Long-term support workhorse with 1M token context |
| **`gemini-1.5-pro`** | Google Gemini 1.5 (LTS) | **Active (LTS)** | Production deep reasoning with 2M token context |
| **`gemma-2-9b-it`** | Google DeepMind (Open Weights)| **Active (Open Source)** | Local/edge inference, open-source institutional equity strategist |

### ⚠️ Deprecated Models (Explicitly Forbidden — Shut Down by Google)
- ❌ **`gemini-1.0-pro` / `gemini-pro`**: Deprecated / discontinued by Google.
- ❌ **`gemini-pro-vision` / `gemini-1.0-pro-vision`**: Shut down. Replaced by native multimodal vision in `gemini-2.5-flash` and `gemini-1.5-flash`.
- ❌ **`gemini-1.0-ultra`**: Deprecated.

---

## 5. Summary of Bugs Encountered & Resolved

1. **`ModuleNotFoundError: No module named 'agents.gemini_audit_agent'` in GitHub Actions CI**:
   - *Cause:* Hyphenated directory name `agents/gemini-audit-agent` cannot be imported with standard Python dotted paths.
   - *Resolution:* Configured `PYTHONPATH=$PWD/agents/gemini-audit-agent:$PYTHONPATH` and imported directly from `core.models` and `core.ledger`.
2. **`RuntimeError: Form data requires 'python-multipart' to be installed`**:
   - *Cause:* FastAPI route `/api/ocr/scan` initially used `UploadFile` and `Form` which requires `python-multipart`.
   - *Resolution:* Refactored `OCRScanRequest` to accept JSON payload with `image_base64` and `notes`, eliminating the external dependency.
3. **`ImportError: cannot import name 'normalize_member_identity'`**:
   - *Cause:* Function in `core/member_resolver.py` is `resolve_canonical_member_id`.
   - *Resolution:* Updated `core/smart_split_tool.py` to call `resolve_canonical_member_id`.
4. **`TypeError: screen_stocks() got an unexpected keyword argument 'filter_mode'`**:
   - *Cause:* `spoke_screener.py` passed `filter_mode` instead of `preset`.
   - *Resolution:* Corrected parameter to `preset="momentum_breakout"` or `"undervalued_quality"`.
5. **`AttributeError: 'StockQuote' object has no attribute 'day_high'`**:
   - *Cause:* `StockQuote` defines `.high`, `.low`, and `.close`.
   - *Resolution:* Updated `spoke_market_feed.py` attributes.
6. **`KeyError: 't1'` in Arthaniti `hub_agent.py`**:
   - *Cause:* `TargetLevels` model uses `t1_conservative`, `t2_base_case`.
   - *Resolution:* Corrected keys in `tools/gemma-quant-mcp/core/hub_agent.py`.
7. **`Hub dispatch error: loadStock is not defined`**:
   - *Cause:* In `tools/gemma-quant-mcp/server.py`, line 742 called `loadStock(sym)` instead of `loadTicker(sym)`.
   - *Resolution:* Changed to `loadTicker(sym)` and added an alias `const loadStock = loadTicker;`.

---

## 6. How to Run, Test, and Verify Everything

### 1. Pre-Flight Guardrail Check (Single Command)
```bash
./deploy_guardrails.sh
```
Runs:
- Python environment verification.
- Bharat Dues Pytest Suite (8 tests).
- Arthaniti Pytest Suite (7 tests).
- Direct mathematical invariant check ($\sum \Delta \equiv 0.00$).
- Service health probe on ports 8000 and 8002.

### 2. Run Bharat Dues Agent (Port 8000)
```bash
cd agents/gemini-audit-agent
python server.py
# Open http://localhost:8000
```

### 3. Run Arthaniti Quant Hub (Port 8002)
```bash
cd tools/gemma-quant-mcp
python server.py
# Open http://localhost:8002
```

---

## 7. File Structure Map

```
open-source-agents/
├── CODEX_GEMMA4_CONTEXT.md          # THIS MASTER CONTEXT FILE
├── README.md                        # Root documentation with architecture map
├── deploy_guardrails.sh             # Pre-flight test & port verification script
├── .github/workflows/
│   └── devfest-agent-ci.yml         # CI workflow enforcing test gates on PRs
├── agents/
│   └── gemini-audit-agent/          # PORT 8000: BHARAT DUES AUDIT AGENT
│       ├── README.md                # Dedicated Bharat Dues documentation
│       ├── .env.example             # Configuration with active models
│       ├── server.py                # FastAPI server + Material 3 Light Web UI
│       ├── main.py                  # CLI demo & audit command
│       ├── requirements.txt         # Pinned dependencies
│       ├── core/
│       │   ├── hub_agent.py         # ADK 4-Spoke Master Hub Agent
│       │   ├── ledger.py            # Double-entry invariant auditor & greedy debt solver
│       │   ├── models.py            # Pydantic schemas (Member, Expense, Settlement, etc.)
│       │   ├── ocr_tool.py          # Multimodal Gemini 2.5 Flash receipt scanner
│       │   ├── smart_split_tool.py  # Exact penny allocation engine (0 drift)
│       │   ├── chat_tool.py         # Conversational financial copilot
│       │   ├── gemini_parser.py     # Unstructured transaction text parser
│       │   └── member_resolver.py   # O(1) canonical member identity resolver
│       └── tests/
│           └── test_audit_ledger.py # 8 Pytest test cases (all passing)
└── tools/
    └── gemma-quant-mcp/             # PORT 8002: ARTHANITI QUANT HUB & MCP
        ├── README.md                # Dedicated Arthaniti documentation
        ├── .env.example             # Configuration with active models
        ├── server.py                # FastAPI server + Dark Terminal UI + A2A Telemetry
        ├── main.py                  # CLI demo & MCP launcher
        ├── mcp_server.py            # JSON-RPC 2.0 Model Context Protocol server
        ├── requirements.txt         # Pinned dependencies
        ├── core/
        │   ├── hub_agent.py         # ADK 5-Spoke Master Hub Agent
        │   ├── models.py            # Pydantic schemas (Quote, Pivots, Invariants, Thesis)
        │   ├── quant_engine.py      # Camarilla, Classic, ATR, Fibonacci mathematics
        │   ├── invariant_guardrails.py # SEBI concentration cap & allocation completeness
        │   ├── market_feed.py       # Live quote fetcher & tick generator
        │   ├── symbol_resolver.py   # Gemma LLM symbol resolver
        │   ├── screener_engine.py   # Momentum breakout & undervalued screener
        │   ├── gemma_advisor.py     # Gemma-2-9B / Gemini 2.5 Flash thesis synthesizer
        │   └── spokes/
        │       ├── spoke_market_feed.py
        │       ├── spoke_camarilla.py (spoke_quant_engine.py)
        │       ├── spoke_risk_guardrail.py
        │       ├── spoke_gemma_advisor.py
        │       └── spoke_screener.py
        └── tests/
            └── test_gemma_quant.py  # 7 Pytest test cases (all passing)
```
