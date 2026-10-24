# Arthaniti Quant Hub & Financial Invariant Engine

> Certified quantitative price target prediction, Camarilla & Classic pivot matrices, double-entry financial invariant guardrails, and Google Gemma-2 / Gemini 2.5 AI equity research synthesis via Model Context Protocol (MCP) and Google ADK Multi-Agent Architecture.

[![Google ADK Hub](https://img.shields.io/badge/Architecture-ADK_Hub_Spoke-blue)](http://localhost:8002)
[![MCP Protocol](https://img.shields.io/badge/Protocol-MCP_JSON--RPC_2.0-green)](http://localhost:8002)
[![Models](https://img.shields.io/badge/Models-Gemma_2_9B_|_Gemini_2.5_Flash-orange)](https://aistudio.google.com/app/apikey)
[![Guardrails](https://img.shields.io/badge/Guardrails-SEBI_<=25%_|_ΣΔ_≡_0.00-purple)](http://localhost:8002)
[![Tests](https://img.shields.io/badge/Tests-7%2F7_Passed-success)](http://localhost:8002)

---

## Overview

### Problem Statement & Domain Focus
- **Strict Domain Boundary**: **Arthaniti** is an institutional quantitative equity research hub designed for NSE/BSE stock analysis, mathematical Camarilla pivot matrices, and portfolio risk guardrails. It is strictly separated from bill-splitting tools (which live in Bharat Dues).
- **Core Problem**: When AI agents and LLMs analyze equities or recommend portfolio allocations, they frequently hallucinate price targets, recommend ungrounded stop-losses, violate SEBI prudential concentration limits ($>25\%$), and introduce floating-point drift.
- **The Solution**: A deterministic mathematical quant engine coupled with a Google ADK Hub-and-Spoke architecture (`urn:adk:hub:arthaniti-quant-master`) that computes exact floor trader bounds in $<10\text{ms}$ and feeds structured data to Google Gemma-2-9B or Gemini 2.5 Flash for institutional thesis synthesis.

### Key Features
- **Certified Camarilla & Classic Pivot Engine**: Computes institutional floor trader price bounds ($H_4, H_3, L_3, L_4, P, R_1-R_3, S_1-S_3$), ATR volatility-adjusted targets, and Fibonacci 1.618 extensions in $<10\text{ms}$.
- **Prudential Portfolio Risk Guardrails**: Enforces SEBI-inspired single-asset concentration limits ($\le 25.0\%$), total allocation completeness ($100.00\%$), and IEEE 754 precision drift protection.
- **Google ADK Hub-and-Spoke Multi-Agent Architecture**: Master Orchestrator coordinating 5 specialized spokes:
  1. `urn:adk:spoke:arthaniti-market-feed` (Live quotes & Gemma LLM ticker resolver)
  2. `urn:adk:spoke:arthaniti-camarilla` (Deterministic Camarilla & Classic pivot matrices)
  3. `urn:adk:spoke:arthaniti-risk-guardrail` (Portfolio allocation and concentration auditor)
  4. `urn:adk:spoke:arthaniti-gemma-advisor` (Gemma-2-9B / Gemini 2.5 institutional thesis synthesis)
  5. `urn:adk:spoke:arthaniti-screener` (Quantitative breadth scanner for momentum & undervalued equities)
- **Model Context Protocol (MCP) Server**: Standard JSON-RPC 2.0 tools for seamless integration into Claude Desktop, Cursor, and Antigravity IDE.
- **Zero-Key Resilient Fast-Path**: 100% functional without an API key using deterministic mathematical models ($0.00 cost, offline-ready).

---

## Model Selection & Support Matrix

Arthaniti provides dynamic model selection in the terminal UI header, REST parameters, and MCP configuration.

### Active & Recommended Models (2025 / 2026)

| Model Name | Tier / Family | Status | Best Used For |
| :--- | :--- | :--- | :--- |
| **`gemini-2.5-flash`** | Google Gemini 2.5 | **Active (Recommended Default)** | Realtime low-latency thesis synthesis, fast pivot interpretation, 1M token context. |
| **`gemma-2-9b-it`** | Google DeepMind (Open Weights) | **Active (Open Source)** | Local/edge inference, open-source institutional equity research thesis. |
| **`gemini-2.5-pro`** | Google Gemini 2.5 | **Active** | Deep multi-step quantitative reasoning and sector rotation analysis. |
| **`gemini-2.5-flash-lite`** | Google Gemini 2.5 | **Active** | High-throughput, ultra-low-latency market scanning. |
| **`gemini-1.5-flash`** | Google Gemini 1.5 (LTS) | **Active (LTS)** | Long-term support production workhorse. |
| **`gemini-1.5-pro`** | Google Gemini 1.5 (LTS) | **Active (LTS)** | Production deep reasoning (2M token context). |

### ⚠️ Deprecated Models (DO NOT USE)
- ❌ **`gemini-1.0-pro` / `gemini-pro`**: Deprecated / discontinued by Google.
- ❌ **`gemini-pro-vision`**: Shut down. Replaced by multimodal `gemini-2.5-flash`.
- ❌ **`gemini-1.0-ultra`**: Deprecated.

---

## How to Enter API Keys

### Method 1: In-Browser Web UI (Easiest)
1. Launch the server (`python server.py`) and visit **`http://localhost:8002`**.
2. Click the **"🔑 API Key"** button in the header.
3. Paste your key from [Google AI Studio](https://aistudio.google.com/app/apikey) and click **"Save & Apply"**.
   - Saved locally in browser `localStorage` (`arthaniti_gemini_api_key`).
   - Header button turns green: **"Key: Active"**.
4. To remove, click **"Clear Key"**.

> **💡 Zero-Key Resilient Mode:** If omitted, Arthaniti automatically runs in **Deterministic Fast-Path Mode** ($0.00 cost, zero token consumption, mathematical certainty).

### Method 2: `.env` Configuration File
```bash
cp .env.example .env
# Edit .env:
GEMINI_API_KEY=AIzaSyYourActualKeyHere
DEFAULT_MODEL=gemini-2.5-flash
```

### Method 3: Shell Environment Variable
```bash
export GEMINI_API_KEY="AIzaSyYourActualKeyHere"
export DEFAULT_MODEL="gemini-2.5-flash"
python server.py
```

---

## How to Run

### 1. Web Terminal & REST API (Port 8002)
```bash
cd tools/gemma-quant-mcp
python server.py
# Open http://localhost:8002 in browser or http://localhost:8002/docs for Swagger
```

### 2. Interactive Rich CLI Demonstration
```bash
python main.py demo
```

### 3. Model Context Protocol (MCP) Server
Integrate with Claude Desktop, Cursor, or Antigravity IDE:
```bash
python main.py mcp
```

### 4. Single-Command Docker Deployment
```bash
docker compose up --build
```

---

## How to Test

Run the automated Pytest suite validating Camarilla pivot mathematics, SEBI portfolio concentration caps, and zero-sum invariant guardrails:

```bash
python3 -m pytest tools/gemma-quant-mcp/tests
```

**Expected output:**
```
============================== 7 passed in 0.17s ===============================
```

---

## Contributor & License
- **Author**: Shikhar Agrawal ([@shikharagrawal17](https://github.com/shikharagrawal17))
- **Event**: Road to DevFest: Open Source Edition | GDG Cloud Bengaluru
- **License**: MIT License © 2026 GDG Cloud Bengaluru Community

---

## 🎥 Video Demonstration & Scene Composition (Brag Skill)

### 🎥 Final Render Paths (Post-Render)
- **Arthaniti Video**: `/Users/shikhar/Projects/open-source-agents/brag-quant/brag.mp4` (also synced at `tools/gemma-quant-mcp/brag/brag.mp4`)

### 🛠️ Current Composition Paths (The Source)
If you want to preview or edit the scenes before rendering:
- **Arthaniti Composition**: `/Users/shikhar/Projects/open-source-agents/brag-quant/composition/index.html` (also at `tools/gemma-quant-mcp/brag/composition/index.html`)
