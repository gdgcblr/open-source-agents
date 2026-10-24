# Gemini Audit Agent

> Autonomous Double-Entry Accounting & Financial Invariant Audit Agent powered by Google Gemini.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: In shared expenses, group settlements, and decentralized accounting, balance drift, aliased participant IDs (e.g. Mixing Firebase UIDs, phone numbers, and local display names), and unconfirmed pending settlements routinely create mathematical discrepancies and interpersonal disputes. Most LLM split tools are superficial wrappers that fail on basic accounting invariants ($ \sum \text{balances} \equiv 0.00 $).
- **Intended Users**:
  - Developers & Maintainers building fintech, splitting, or ledger applications.
  - Roommates, travel groups, and event organizers settling shared expenses over UPI or bank transfers.
  - Financial auditors seeking automated mathematical verification of unstructured transaction records.

### Key Features
- **Deterministic Invariant Enforcement**: Proves and enforces double-entry conservation ($\sum \text{balances} \equiv 0.00$) with precision rounding guardrails.
- **Universal Canonical Member Indexing**: $O(1)$ hash indexer that folds fragmented participant IDs (Firebase Auth UIDs, normalized phone numbers, and names) into canonical member entities.
- **Dual-Layer Parser (Gemini + Local Fallback)**: Extracts structured ledgers using Google Gemini 1.5 Flash when online, backed by an instant deterministic local heuristic regex parser ($0.00 cost, offline-capable).
- **Pending vs. Confirmed Settlement Isolation**: Isolates unverified pending payments to prevent ledger corruption while providing optimal settlement paths.
- **Single-Command Startup & Web Dashboard**: Zero-configuration Docker launch (`docker compose up`) with built-in interactive visual dashboard and REST API.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: Google Generative AI (`google-generativeai`), Pydantic v2, Click, Rich CLI
- **API Server & Web UI**: FastAPI, Uvicorn, Single Page Application HTML/JS
- **Containerization**: Docker, Docker Compose, Nginx/Python Alpine
- **Models**: Google Gemini 1.5 Flash (with offline deterministic regex fallback)
- **Testing**: Pytest

---

## Architecture & Data Flow

```
[Raw Input: Chat / Bill / Receipt]
               |
               v
  +--------------------------+
  | Dual-Layer AI Parser     |
  |  - Google Gemini Flash   |
  |  - Local Regex Fallback  |
  +--------------------------+
               |
               v
  +--------------------------+
  | O(1) Canonical Indexer   |  <-- Resolves UIDs, phone numbers, and names
  +--------------------------+
               |
               v
  +--------------------------+
  | Double-Entry Invariant   |  <-- Enforces sum(balances) == 0.00
  | Ledger Engine            |  <-- Isolates unconfirmed settlements
  +--------------------------+
         |            |
         v            v
  [Anomalies]   [Greedy Minimal Settlement Graph]
         |            |
         +------+-----+
                |
                v
   [Rich CLI / REST / Web UI]
```

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.10+ (or Docker & Docker Compose)
- A Google Gemini API Key from [Google AI Studio](https://aistudio.google.com/app/apikey) *(Optional: The agent features an offline mock heuristic mode that works out-of-the-box without an API key)*

---

## Installation & Setup

### Option A: Single-Command Docker (Recommended)

1. **Navigate to the project folder:**
   ```bash
   cd agents/gemini-audit-agent
   ```

2. **Copy the environment configuration:**
   ```bash
   cp .env.example .env
   ```

3. **Start the container:**
   ```bash
   docker compose up
   ```
   Open your browser at **`http://localhost:8000`** to access the interactive web dashboard.

---

### Option B: Local Python Environment

1. **Navigate to the project folder:**
   ```bash
   cd agents/gemini-audit-agent
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment:**
   ```bash
   cp .env.example .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | No | *Empty* | Google Gemini API key. If empty, runs in offline heuristic mode. |
| `GEMINI_MODEL` | No | `gemini-1.5-flash` | Gemini model identifier |
| `PORT` | No | `8000` | HTTP port for server and web dashboard |
| `HOST` | No | `0.0.0.0` | Bind host address |
| `DEFAULT_CURRENCY` | No | `INR` | Default currency label |

---

## How to Run

### 1. Interactive Demo Showcase
Runs the exact DevFest edge-case reproduction showing ID alias resolution, balance calculation, and pending payment isolation:
```bash
python main.py demo
```

### 2. Audit Unstructured Text via CLI
```bash
python main.py audit --text "Dinner of 3000 paid by Alice split with Bob. Bob paid Alice 1400 pending."
```

### 3. Start the Web Dashboard & API Server
```bash
python server.py
# Open http://localhost:8000
```

---

## Example Input & Output

### Example Input
```
"Transaction of 3000 paid by Alice split with Bob. Bob paid Alice 1400 pending confirmation."
```

### Example Terminal Output
```
🔍 Financial Audit Summary
Total Volume Audited: ₹3,000.00
Status: BALANCED (Mathematical Invariant Verified: ∑ = 0.00)
Net Zero Check Delta: ₹0.0000
Pending Unverified Payments: 1

📊 Audited Member Balances
Member               Net Balance         Ledger Position
Alice                +₹1,500.00          Gets Back (Creditor)
Bob                  -₹1,500.00          Owes (Debtor)

⚠️ Detected Anomalies & Integrity Warnings
Type                 Severity     Description                                Suggested Fix
PENDING_HOLD         LOW          1 unverified payment(s) total ₹1400.00     Notify recipient to confirm receipt.

⚡ Optimal Settlement Path (Greedy Match)
Payer (From)         Amount       Payee (To)          UPI / Action
Bob                  ₹1,500.00    Alice               Pay via UPI: alice@upi
```

---

## How to Test

Run the automated test suite verifying mathematical invariants, ID resolution, and split precision:

```bash
pytest
```

**Expected output:**
```
tests/test_audit_ledger.py .....                                         [100%]
============================== 5 passed in 0.10s ===============================
```

---

## Known Limitations

- Multi-currency conversions currently assume fixed exchange rates unless an external forex API key is configured.
- Receipt images larger than 20MB should be resized prior to sending to the multimodal Gemini endpoint.
- Deep historical transaction graphs exceeding 50,000 nodes are batched in memory and may require an external database back-end for long-term audit persistence.

---

## Security & Privacy Considerations

- **Zero Tracked Credentials**: No API keys, credentials, or `.env` files are tracked in source control.
- **Offline Resiliency**: Operates fully offline using deterministic regex heuristics if no external credentials are provided.
- **Sandboxed Execution**: The agent does not execute arbitrary shell commands or unsandboxed code.

---

## Future Improvements

- [ ] Add direct Model Context Protocol (MCP) server endpoints for Claude Desktop and Antigravity IDE integration.
- [ ] Support on-device Gemma via MediaPipe LLM Inference for completely private, zero-cloud execution.
- [ ] Add PDF invoice ingestion with automated OCR tabular itemization.

---

## License

This project is contributed under the repository's [MIT License](../../LICENSE) © 2026 GDG Cloud Bengaluru Community.
