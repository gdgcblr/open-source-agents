# Bharat Dues AI Audit Agent

> Autonomous Double-Entry Accounting & Financial Invariant Audit Agent powered by Google Gemini, Google ADK Hub-and-Spoke Architecture, and Multimodal OCR. Companion agent to [Bharat Dues](https://bharat-dues.web.app).

[![DevFest Guardrails](https://img.shields.io/badge/DevFest-Guardrails_Verified-emerald)](https://bharat-dues.web.app)
[![Google ADK Hub](https://img.shields.io/badge/Architecture-ADK_Hub_Spoke-blue)](https://bharat-dues.web.app)
[![Model Support](https://img.shields.io/badge/Models-Gemini_2.5_Flash_|_Gemma_2-orange)](https://aistudio.google.com/app/apikey)
[![Invariant Math](https://img.shields.io/badge/Invariant-ΣΔ_≡_0.00-purple)](https://bharat-dues.web.app)
[![Tests](https://img.shields.io/badge/Tests-8%2F8_Passed-success)](https://github.com)

---

## Overview

### Problem Statement & Domain Focus
- **Strict Domain Boundary**: **Bharat Dues** is strictly focused on **shared group bill splitting, multimodal receipt scanning, double-entry mathematical auditing, and 1-tap NPCI UPI settlements**. It is completely decoupled from equity stock market tools (which live separately in Arthaniti).
- **Core Problem**: In group travel, flatmate expenses, and decentralized ledgers, balance drift, aliased participant identities (Firebase UIDs vs. phone numbers vs. display names), and unconfirmed pending settlements routinely create mathematical discrepancies and disputes. Most LLM-based split apps are superficial wrappers that hallucinate calculations and violate basic accounting invariants ($\sum \text{balances} \equiv 0.00$).
- **The Solution**: An autonomous Google ADK Hub-and-Spoke agent that enforces mathematical double-entry invariants, provides multimodal Gemini receipt OCR with drag-and-drop file upload, delivers exact zero-drift penny allocation splitting, and isolates unverified pending transactions.

### Key Features
- **Deterministic Invariant Enforcement**: Proves and enforces double-entry conservation ($\sum \text{balances} \equiv 0.00$) with zero floating-point precision drift.
- **Google ADK Hub-and-Spoke Multi-Agent Architecture**: Central orchestrator (`urn:adk:hub:bharat-dues-master`) coordinating 4 specialized spokes:
  1. `urn:adk:spoke:bharat-dues-ledger` (Double-entry balance auditor & anomaly detector)
  2. `urn:adk:spoke:receipt-ocr` (Multimodal Gemini 2.5 Flash bill and receipt vision scanner)
  3. `urn:adk:spoke:smart-split` (Zero-drift penny allocation engine with percentage & custom sliders)
  4. `urn:adk:spoke:settlement-upi` (Greedy minimal-debt graph solver & 1-tap NPCI UPI deep links)
- **Multimodal Receipt OCR with File Drag-and-Drop**: Upload receipt images (JPEG/PNG/WebP) or choose instant mock presets (Swiggy, Taj Goa, Third Wave Coffee) with live line-item itemization.
- **Conversational Financial Copilot**: Natural language AI chat assistant for rapid expense logging, balance sheet inquiries, and dispute audits.
- **Material 3 Light Design**: Clean, high-contrast, production-grade Material 3 theme matching [bharat-dues.web.app](https://bharat-dues.web.app) (zero dark glassmorphism).
- **Zero-Key Resilient Fallback**: 100% functional out-of-the-box without an API key using deterministic heuristics ($0.00 cost, offline-ready).

---

## Model Selection & Support Matrix

Bharat Dues supports dynamic model selection via in-browser UI dropdown, REST query parameters, or environment variables.

### Active & Recommended Models (2025 / 2026)

| Model Name | Tier / Family | Status | Best Used For |
| :--- | :--- | :--- | :--- |
| **`gemini-2.5-flash`** | Google Gemini 2.5 | **Active (Recommended Default)** | **Primary choice.** Ultra-fast multimodal OCR, low-latency conversational chat, 1M token context window. |
| **`gemini-2.5-pro`** | Google Gemini 2.5 | **Active** | Complex multi-party disputes, long historical balance sheet audits, deep financial reasoning. |
| **`gemini-2.5-flash-lite`** | Google Gemini 2.5 | **Active** | Ultra low-latency, lightweight receipt itemization at minimal token footprint. |
| **`gemini-1.5-flash`** | Google Gemini 1.5 (LTS) | **Active (LTS)** | Production workhorse with 1M token context, high stability and proven rate limits. |
| **`gemini-1.5-pro`** | Google Gemini 1.5 (LTS) | **Active (LTS)** | Long-context ledger audits (up to 2M tokens). |
| **`gemma-2-9b-it`** | Google DeepMind (Open Weights) | **Active (Open Source)** | Local/edge inference, open-source compliance. |

### ⚠️ Deprecated Models (DO NOT USE — Shut Down by Google)
- ❌ **`gemini-1.0-pro` / `gemini-pro`**: Deprecated and shut down.
- ❌ **`gemini-pro-vision` / `gemini-1.0-pro-vision`**: Shut down. Replaced by native multimodal vision in `gemini-2.5-flash` and `gemini-1.5-flash`.
- ❌ **`gemini-1.0-ultra`**: Deprecated.

---

## How to Enter API Keys for Google Gemini

You can configure your Google Gemini API key in any of the following 3 ways:

### Method 1: In-Browser UI (Fastest & Easiest — Recommended for Demos)
1. Launch the web application: `python server.py` and navigate to **`http://localhost:8000`**.
2. In the top navigation bar, click the **"🔑 Configure API Key"** button.
3. Paste your free API key obtained from [Google AI Studio](https://aistudio.google.com/app/apikey).
4. Click **"Save & Apply"**.
   - The key is securely saved in your browser's `localStorage` (`bharat_dues_gemini_api_key`).
   - The header button immediately turns green: **"Key: Active (AI Studio)"**.
   - All subsequent OCR scans, chat interactions, and audit dispatches will automatically use your live Gemini key.
5. To reset or remove the key, click the button again and choose **"Clear Key"**.

> **💡 Zero-Key Resilient Mode:** If you do not enter an API key, Bharat Dues automatically runs in **Deterministic Heuristic Mode**. It uses deterministic regex parsers and pre-loaded authentic receipt templates ($0.00 cost, 100% offline-ready, 0 crash risk during live stage presentations).

---

### Method 2: `.env` Configuration File
1. Copy the example configuration:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` and add your key:
   ```bash
   GEMINI_API_KEY=AIzaSyYourActualKeyHere
   GEMINI_MODEL=gemini-2.5-flash
   ```

---

### Method 3: Shell Environment Variable
Export the key directly in your terminal before launching:
```bash
export GEMINI_API_KEY="AIzaSyYourActualKeyHere"
export GEMINI_MODEL="gemini-2.5-flash"
python server.py
```

---

## How to Run

### Option A: Local Python Server & Material 3 Web UI (Port 8000)
1. **Navigate to project directory:**
   ```bash
   cd agents/gemini-audit-agent
   ```
2. **Create & activate virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Launch the server:**
   ```bash
   python server.py
   ```
5. Open **`http://localhost:8000`** in your browser.
   - Use the **Global Model Selector** in the header to switch between `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-1.5-flash`, etc.
   - Click **"🔑 Configure API Key"** to enter your AI Studio key.
   - Switch between the 4 workspace tabs:
     1. **AI Chat Copilot**: Conversational expense logging and ledger querying.
     2. **Smart Receipt OCR**: Drag-and-drop receipt image scanner.
     3. **Smart Split Calculator**: Dynamic members, penny-accurate conservation.
     4. **Double-Entry Audit**: Invariant verification and greedy NPCI UPI settlement path.

---

### Option B: Single-Command Docker Deployment
```bash
cd agents/gemini-audit-agent
docker compose up --build
```
Open **`http://localhost:8000`** in your browser.

---

### Option C: Interactive CLI Showcase
Run the built-in terminal demonstration showcasing canonical ID resolution, invariant math, and pending payment isolation:
```bash
python main.py demo
```

Audit unstructured transaction text directly from your terminal:
```bash
python main.py audit --text "Dinner of 3000 paid by Alice split with Bob. Bob paid Alice 1400 pending."
```

---

## Technical Stack & Architecture

- **Language & Runtime**: Python 3.9+ / 3.11+
- **Agent Architecture**: Google Agent Development Kit (ADK) Hub-and-Spoke Pattern (`urn:adk:hub:bharat-dues-master`)
- **Multimodal AI**: Google Gemini 2.5 Flash / 1.5 Flash Vision & Text
- **Web Framework**: FastAPI & Uvicorn
- **Frontend**: Material 3 Light Single Page Application (Tailwind CSS, Inter Font, Zero Glassmorphism)
- **Settlement Protocol**: NPCI UPI Deep Links (`upi://pay?pa=...&am=...&cu=INR`)
- **Testing**: Pytest

```
                   ┌────────────────────────────────────────┐
                   │        Bharat Dues Master Hub          │
                   │    (urn:adk:hub:bharat-dues-master)    │
                   └───────────────────┬────────────────────┘
                                       │
         ┌──────────────────┬──────────┴──────────┬──────────────────┐
         ▼                  ▼                     ▼                  ▼
┌──────────────────┐┌──────────────────┐┌──────────────────┐┌──────────────────┐
│ Spoke 1: Ledger  ││  Spoke 2: OCR    ││ Spoke 3: Split   ││ Spoke 4: Settle  │
│ Double-Entry     ││ Multimodal Vision││ Exact Penny-Math ││ Greedy Debt Graph│
│ (∑ Δ ≡ 0.00)     ││ Gemini 2.5 Flash ││ (0 Penny Drift)  ││ NPCI UPI Links   │
└──────────────────┘└──────────────────┘└──────────────────┘└──────────────────┘
```

---

## Mathematical Invariant Proof

For any audited financial group ledger containing members $M$, expenses $E$, and settlements $S$:

$$\sum_{m \in M} \text{NetBalance}(m) \equiv 0.00$$

Where:
- $\text{NetBalance}(m) = \sum \text{PaidBy}(m) - \sum \text{ShareOf}(m) + \sum \text{SettledIn}(m) - \sum \text{SettledOut}(m)$
- **Conservation Law**: If $|\sum \text{NetBalance}| > 0.0001$, the transaction is mathematically rejected with a `BALANCE_DRIFT` integrity breach.
- **Pending Payment Quarantine**: All unconfirmed settlements are strictly isolated in a quarantine queue so they cannot corrupt active balances.

---

## How to Test

Run the automated test suite verifying mathematical invariants, ID resolution, multimodal OCR fallbacks, and smart split precision:

```bash
python3 -m pytest agents/gemini-audit-agent/tests
```

**Expected output:**
```
============================== 8 passed in 0.17s ===============================
```

---

## REST API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/healthz` | Health check, ADK Hub topology, and registered capabilities |
| `GET` | `/api/hub/spokes` | Lists all 4 ADK spokes and online statuses |
| `POST` | `/api/hub/chat` | Dispatches natural language query to Master Hub |
| `POST` | `/api/ocr/scan` | Multimodal receipt scan (accepts `image_base64`, `model`, `api_key`) |
| `POST` | `/api/split/calculate` | Exact penny allocation calculation |
| `POST` | `/api/chat` | Conversational financial copilot |
| `POST` | `/api/audit` | Audits raw transaction text for double-entry invariants |
| `GET` | `/docs` | Interactive OpenAPI / Swagger documentation |

---

## Contributor & License

- **Live Production App**: [https://bharat-dues.web.app](https://bharat-dues.web.app)
- **Author**: Shikhar Agrawal ([@shikharagrawal17](https://github.com/shikharagrawal17))
- **Event**: Road to DevFest: Open Source Edition | GDG Cloud Bengaluru
- **License**: MIT License © 2026 GDG Cloud Bengaluru Community

---

## 🎥 Video Demonstration & Scene Composition (Brag Skill)

### 🎥 Final Render Paths (Post-Render)
- **Bharat Dues Video**: `brag-audit/brag.mp4` (also synced at `agents/gemini-audit-agent/brag/brag.mp4`)

### 🛠️ Current Composition Paths (The Source)
If you want to preview or edit the scenes before rendering:
- **Bharat Dues Composition**: `brag-audit/composition/index.html` (also at `agents/gemini-audit-agent/brag/composition/index.html`)
