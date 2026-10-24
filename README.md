# Open Source AI Agents & Developer Tools Monorepo

> **Road to DevFest 2026: Open Source Edition | GDG Cloud Bengaluru at Google Ananta, Bengaluru**  
> Curated, production-grade AI agents, developer tooling, and Model Context Protocol (MCP) servers built with Google Agent Development Kit (ADK), Google Gemini 2.5 / Gemma 2, and deterministic financial invariant guardrails.

---

## 🏛️ Featured Projects Overview

This repository houses two decoupled, production-grade Google AI projects:

```
                                  open-source-agents/
                                           │
         ┌─────────────────────────────────┴─────────────────────────────────┐
         ▼                                                                   ▼
┌────────────────────────────────────────┐         ┌────────────────────────────────────────┐
│  agents/gemini-audit-agent             │         │  tools/gemma-quant-mcp                 │
│  "Bharat Dues AI Audit Agent"          │         │  "Arthaniti Quant Hub & MCP"           │
│  Port: 8000                            │         │  Port: 8002                            │
│  Companion: https://bharat-dues.web.app│         │  Protocol: MCP JSON-RPC 2.0 / REST     │
├────────────────────────────────────────┤         ├────────────────────────────────────────┤
│ • Double-Entry Audit (∑Δ ≡ 0.00)       │         │ • Certified Camarilla & Classic Pivots │
│ • Multimodal Gemini 2.5 Flash OCR      │         │ • SEBI Risk Concentration Cap (≤25%)   │
│ • Smart Split (Zero Penny Drift)       │         │ • Gemma-2-9B Institutional Thesis      │
│ • Conversational Financial Copilot     │         │ • High-Conviction Equity Screener      │
│ • Greedy NPCI UPI Deep Links           │         │ • A2A Realtime Telemetry Dispatch      │
│ • Material 3 Light Theme UI            │         │ • Model Context Protocol (MCP) Server  │
└────────────────────────────────────────┘         └────────────────────────────────────────┘
```

---

## 🚀 Quick Start: Running the Projects

### Single-Command Pre-Flight Verification
Run all 15 automated test cases, check mathematical invariants, and verify service health across both ports:
```bash
./deploy_guardrails.sh
```

---

### Project 1: Bharat Dues AI Audit Agent (Port 8000)
1. **Navigate & Install:**
   ```bash
   cd agents/gemini-audit-agent
   pip install -r requirements.txt
   ```
2. **Start Server:**
   ```bash
   python server.py
   ```
3. **Open Web App:** Visit **`http://localhost:8000`** in your browser.
   - Material 3 Light Theme matching production [https://bharat-dues.web.app](https://bharat-dues.web.app).
   - 4 Workspace Tabs: AI Chat Copilot, Receipt OCR, Smart Split, Double-Entry Audit.
   - Live Swagger Documentation: `http://localhost:8000/docs`.

---

### Project 2: Arthaniti Quant Hub & MCP Engine (Port 8002)
1. **Navigate & Install:**
   ```bash
   cd tools/gemma-quant-mcp
   pip install -r requirements.txt
   ```
2. **Start Server:**
   ```bash
   python server.py
   ```
3. **Open Web Terminal:** Visit **`http://localhost:8002`** in your browser.
   - Live Swagger Documentation: `http://localhost:8002/docs`.
4. **Run as Model Context Protocol (MCP) Server:**
   ```bash
   python main.py mcp
   ```
   Exposes standard JSON-RPC tools (`calculate_quant_targets`, `audit_invariants`, `screen_stocks`, `generate_gemma_thesis`) for Claude Desktop, Cursor, and Antigravity IDE.

---

## 🔑 How to Enter Gemini API Keys & Select Models

### 3 Flexible Ways to Enter Your API Key:
1. **In-Browser UI Modal (Recommended for Live Demos)**:
   - Click the **"🔑 Configure API Key"** button in the header of either web app (Port 8000 or Port 8002).
   - Paste your free key from [Google AI Studio](https://aistudio.google.com/app/apikey) and click **"Save & Apply"**.
   - Stored safely in browser `localStorage`. Status indicator turns green: **"Key: Active"**.
2. **Environment File (`.env`)**:
   - Copy `.env.example` to `.env` in the project folder and set `GEMINI_API_KEY=AIzaSy...`.
3. **Terminal Environment Variable**:
   - `export GEMINI_API_KEY="AIzaSy..."` before launching.

> **💡 Zero-Key Resilient Mode:** If no key is entered, **both agents operate in Deterministic Heuristic Fast-Path Mode** ($0.00 cost, 100% offline-ready, 0 crash risk during live stage presentations).

---

## 🧠 Model Selection & Deprecation Matrix

Both agents feature an interactive in-browser dropdown to select the active AI model:

| Model Identifier | Model Family | Status | Best Use Case |
| :--- | :--- | :--- | :--- |
| **`gemini-2.5-flash`** | Google Gemini 2.5 | **Active (Recommended Default)** | Realtime multimodal receipt OCR, low-latency chat, fast thesis synthesis |
| **`gemini-2.5-pro`** | Google Gemini 2.5 | **Active** | Complex multi-party dispute resolution, long balance sheet audits |
| **`gemini-2.5-flash-lite`**| Google Gemini 2.5 | **Active** | Ultra low-latency, lightweight processing |
| **`gemini-1.5-flash`** | Google Gemini 1.5 (LTS) | **Active (LTS)** | Production workhorse (1M token context) |
| **`gemini-1.5-pro`** | Google Gemini 1.5 (LTS) | **Active (LTS)** | High-complexity reasoning (2M token context) |
| **`gemma-2-9b-it`** | Google DeepMind (Open Weights)| **Active (Open Source)** | Local/edge inference, open-source institutional equity thesis |

### ⚠️ Deprecated Models (Do NOT Use — Shut Down by Google):
- ❌ `gemini-1.0-pro` / `gemini-pro`: Deprecated / discontinued.
- ❌ `gemini-pro-vision` / `gemini-1.0-pro-vision`: Shut down (replaced by native multimodal `gemini-2.5-flash`).
- ❌ `gemini-1.0-ultra`: Deprecated.

---

## 🧪 Testing & CI/CD Guardrails

Execute tests locally:
```bash
# Test Bharat Dues Agent (8 tests)
python3 -m pytest agents/gemini-audit-agent/tests

# Test Arthaniti Quant Hub (7 tests)
python3 -m pytest tools/gemma-quant-mcp/tests
```

Both test suites are automatically enforced in GitHub Actions (`.github/workflows/devfest-agent-ci.yml`) on every pull request to ensure that no balance drift or arithmetic violation ever reaches `main`.

---

## 📜 License & Acknowledgments

- **License**: MIT License © 2026 GDG Cloud Bengaluru Community.
- **Event**: Road to DevFest: Open Source Edition | GDG Cloud Bengaluru at Google Ananta, Bengaluru.
- **Contributor**: Shikhar Agrawal ([@shikharagrawal17](https://github.com/shikharagrawal17))
