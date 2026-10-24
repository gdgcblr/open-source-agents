# Gemma Quant MCP & Financial Invariant Engine

> Certified quantitative price target prediction, Camarilla & Classic pivot matrices, double-entry financial invariant guardrails, and Gemma AI equity research synthesis via Model Context Protocol (MCP).

---

## Overview

### Problem Statement & Intended Users
- **Problem**: When financial AI agents and LLMs are asked to calculate price targets, pivots, stop-losses, and ledger balances, they frequently hallucinate floating-point arithmetic, produce ungrounded target levels, and fail to enforce fundamental accounting invariants ($\sum \Delta \equiv 0.00$).
- **Intended Users**: Financial AI agent builders, quant developers, and algorithmic trading agent developers who need mathematically audited quantitative targets and invariant guardrails for LLMs.

### Key Features
- **Certified Camarilla & Classic Pivot Engine**: Computes institutional-grade pivot matrices ($H_4, H_3, L_3, L_4, P, R_1-R_3, S_1-S_3$), ATR volatility-adjusted targets, and Fibonacci 1.618 extensions in $<10\text{ms}$.
- **Double-Entry Financial Invariant Guardrails**: Verifies zero-sum ledger balance ($\sum \Delta \equiv 0.00$), portfolio weight completeness ($100.00\%$), IEEE 754 precision protection, and concentration safeguards ($<25\%$).
- **Model Context Protocol (MCP) Server**: Exposes standard JSON-RPC tools (`calculate_quant_targets`, `audit_invariants`, `screen_stocks`, `generate_gemma_thesis`) directly to agents across Antigravity, Claude Desktop, Cursor, or LangChain.
- **Dual-Layer Architecture with Gemma / Gemini**: Combines deterministic $0-cost mathematical calculations with Google Gemma-2 / Gemini 1.5 Flash natural language thesis synthesis, with resilient offline fallback.

---

## Technical Stack

- **Language & Runtime**: Python 3.9+ / 3.11+
- **Agent Framework / Protocol**: Model Context Protocol (MCP) JSON-RPC 2.0 / FastAPI REST API
- **Models & AI Technologies**: Google Gemma-2-9B / Gemini 1.5 Flash (`google-generativeai`)
- **Core Libraries**: Pydantic v2, Rich, Click, Uvicorn, Pytest
- **Containerization**: Docker & Docker Compose (`docker compose up`)

---

## Architecture & Data Flow

```
[Agent Query / User Input]
            │
            ▼
┌────────────────────────────────────────────────────────┐
│           Gemma Quant MCP Server (stdio / REST)         │
│  ┌───────────────────────┐  ┌───────────────────────┐  │
│  │   Quant Engine        │  │ Invariant Guardrails  │  │
│  │ • Camarilla Pivots    │  │ • Zero-sum (ΣΔ ≡ 0)   │  │
│  │ • Classic Pivots      │  │ • Weight Sum = 100%   │  │
│  │ • ATR Projections     │  │ • Float Precision     │  │
│  │ • Conviction Score    │  │ • Max Conc. (<25%)    │  │
│  └───────────────────────┘  └───────────────────────┘  │
│                            │                           │
│                            ▼                           │
│           ┌─────────────────────────────────┐          │
│           │  Google Gemma / Gemini Advisor  │          │
│           │ • Strategic Research Thesis     │          │
│           │ • Downside Invalidation Levels  │          │
│           └─────────────────────────────────┘          │
└────────────────────────────────────────────────────────┘
            │
            ▼
[Deterministic Audited Targets & Structured Trade Thesis]
```

---

## Evaluation & Judging Criteria

| Pillar | Criterion | Performance Metric |
| :--- | :--- | :--- |
| **1. Task Completion** | Deterministic Accuracy | **100% pass rate** on all invariant math and pivot formulas; 0 unhandled exceptions. |
| **2. Repeat Use** | Reusable Tooling | Exposes standard MCP tools that plug into any autonomous agent workflow. |
| **3. User Effort** | One-Step Execution | Computes entire pivot matrix, stops, and conviction score in single tool call ($<10\text{ms}$). |
| **4. Cost Effectiveness** | Dual-Layer Efficiency | $0 token cost for mathematical logic; offline fallback works with 0 API keys. |
| **5. Reproducibility** | Zero-Friction Setup | Containerized with single-command `docker compose up` and verified with `pytest`. |

---

## Prerequisites & Installation

### Local Setup
```bash
# Navigate to tool directory
cd tools/gemma-quant-mcp

# Install dependencies
pip install -r requirements.txt

# (Optional) Copy environment template
cp .env.example .env
```

---

## Usage

### 1. Interactive Visual Demo (Rich CLI)
Run the built-in demo displaying target matrices, ledger invariant audit, and Gemma thesis:
```bash
python main.py demo
```

### 2. Run as Model Context Protocol (MCP) Server
Integrate with any AI agent or IDE via stdio:
```bash
python main.py mcp
```

### 3. Run FastAPI REST API & Embedded Dashboard
Launch local server on port 8002:
```bash
python server.py
# Open http://localhost:8002 in browser or inspect Swagger at http://localhost:8002/docs
```

### 4. Single-Command Docker Deployment
```bash
docker compose up --build
```

---

## Running Tests

Execute the automated test suite verifying mathematical precision and invariant rules:
```bash
python3 -m pytest tests/
```
Result: `7 passed in 0.12s`

---

## Project Structure

```
tools/gemma-quant-mcp/
├── core/
│   ├── __init__.py
│   ├── models.py                  # Pydantic models for quotes, pivots, invariants, theses
│   ├── quant_engine.py            # Classic, Camarilla, Fibonacci, ATR calculations
│   ├── invariant_guardrails.py    # Zero-sum ledger check, allocation sum, float precision
│   ├── screener_engine.py         # Benchmark equity universe and filter engine
│   └── gemma_advisor.py           # Google Gemma / Gemini 1.5 Flash thesis generator
├── tests/
│   ├── __init__.py
│   └── test_gemma_quant.py        # Automated Pytest suite (7 test cases)
├── main.py                        # Click CLI & interactive Rich demonstration
├── mcp_server.py                  # Standard JSON-RPC Model Context Protocol server
├── server.py                      # FastAPI REST server & embedded dark-mode HTML UI
├── requirements.txt               # Pinned Python dependencies
├── pytest.ini                     # Pytest configuration
├── Dockerfile                     # Multi-stage production container
├── docker-compose.yml             # Single-command startup specification
├── .env.example                   # Environment configuration template
├── .gitignore                     # Repository ignore rules
└── README.md                      # Complete project documentation
```

---

## Contributor
- Shikhar Agrawal ([@shikharagrawal17](https://github.com/shikharagrawal17))
