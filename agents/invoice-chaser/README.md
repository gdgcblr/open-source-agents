# Invoice Chaser

> An AI agent that helps freelancers and small agencies get paid on time — it reconciles bank payments to invoices, drafts tone-appropriate payment reminders, and tracks client promises, while keeping every number grounded in a deterministic ledger and every outgoing message under human approval.

> **Status:** 🚧 Design phase. See [docs/PRODUCT.md](docs/PRODUCT.md) and [docs/TECHNICAL_SCOPING.md](docs/TECHNICAL_SCOPING.md). Sections marked *TBD* will be completed with implementation.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Freelancers send invoices and then spend hours chasing payments — matching cryptic bank references (often short-paid due to TDS) to invoices, remembering who to follow up with, and agonising over how to word reminders without damaging client relationships.
- **Intended Users**: Independent freelancers and small agencies (5–20 active clients) who invoice by email and get paid by bank transfer.

### Key Features
- **Payment reconciliation**: Matches bank statement lines to invoices, including TDS short-payments and payer-name variations, with confidence scores. Uncertain matches go to the user.
- **Chase list**: Deterministic ageing and prioritisation of overdue invoices.
- **Tone-ladder reminder drafts**: Friendly → firm → final, in English or Hinglish, personalised per client — with amounts and dates filled from the ledger, never typed by the LLM.
- **Human approval queue**: Approve, edit, soften/firm-up, or skip every draft. Nothing is ever sent automatically.
- **Reply understanding**: Paste a client's reply; the agent detects promises-to-pay, disputes, "already paid" claims, and proposes the right ledger update.
- **Audit trail**: Every change records who made it and why.
- **MCP server**: The ledger tools are exposed over Model Context Protocol, so any MCP client can query "who owes me money?"

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) — root agent + sub-agents; ledger tools served by a **Model Context Protocol (MCP) server** and consumed via ADK `MCPToolset`
- **Models**: Gemini (Flash tier by default, configurable via `MODEL_NAME`) through a Google AI Studio API key. A mock model is used for tests, so `pytest` runs with no key.
- **External APIs / Tools**: SQLite (local file). No third-party integrations in v1.
- **Interface**: `adk web` (ADK dev UI, shows tool-call traces) + a small CLI for imports and the approval queue

---

## Architecture & Data Flow

```
┌─────────────────────────────────────────────────────────┐
│  INTERFACE (CLI)   import · chase run · review · reply  │
└───────────────▲──────────────────────┬──────────────────┘
                │ summaries, drafts    │ commands, approvals
┌───────────────┴──────────────────────▼──────────────────┐
│  AGENT LAYER (LLM — judgement only)                     │
│  Orchestrator → Matcher · Drafter · Reply Classifier    │
└───────────────▲──────────────────────┬──────────────────┘
                │ facts (JSON)         │ validated tool calls
┌───────────────┴──────────────────────▼──────────────────┐
│  TOOL LAYER (deterministic code, also an MCP server)    │
│  Ledger · Ageing/Priority · Policy · Renderer ·         │
│  Approval Queue · Audit Log                             │
└───────────────▲──────────────────────┬──────────────────┘
                └──────── SQLite ──────┘
```

**Core rule:** the agent proposes, the tool disposes. The LLM never computes money or dates and never writes to storage directly. Reminder drafts use template slots (`{amount_due}`, `{due_date}`) that the tool fills from the ledger; drafts containing raw numbers are rejected.

Full flows, state machines, tool contracts, failure handling and evals: [docs/TECHNICAL_SCOPING.md](docs/TECHNICAL_SCOPING.md).

---

## Prerequisites

- Python 3.10+
- pip
- A Google AI Studio API key (free tier works) — get one at https://aistudio.google.com/apikey. Not needed to run the test suite.

---

## Installation & Setup

*TBD — will be completed and verified on a clean clone during implementation.*

---

## Configuration & Environment Variables

*TBD — expected variables:*

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | Yes (to run the agent) | *None* | Google AI Studio API key for Gemini |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | `FALSE` | Keep `FALSE` to use AI Studio |
| `MODEL_NAME` | No | *Gemini Flash-tier, set at implementation* | Gemini model identifier |
| `INVOICE_CHASER_DB` | No | `./data/ledger.db` | Path to the local SQLite ledger |
| `LOG_LEVEL` | No | `info` | Logging verbosity |

---

## How to Run

*TBD.*

---

## Example Input & Output

*TBD — will be populated from genuine runs on the bundled sample dataset.*

---

## How to Test

*TBD — planned: `pytest` (unit, invariant and mock-model flow tests, no key needed) and `adk eval` (evalsets checking tool-call paths and responses). Layers: unit tests (tool logic), flow tests with mock LLM, component evals (matcher / drafter / reply classifier), end-to-end scenario evals, and red-team evals for prompt injection. See [docs/TECHNICAL_SCOPING.md §7](docs/TECHNICAL_SCOPING.md#7-evals).*

---

## Known Limitations

*Planned v1 constraints:*
- Does not send emails or messages — drafts only.
- No live bank or inbox integration; statements and replies are imported/pasted manually.
- No OCR for PDF/photo invoices.
- Foreign-currency payments are only matched against same-currency invoices.

---

## Security & Privacy Considerations

- **Secrets Handling**: API keys loaded from a local `.env` (git-ignored); only `.env.example` is committed.
- **Data Privacy**: Client names, invoice numbers and amounts are sent to Google's Gemini API for matching and drafting. Bank account numbers are not sent. The test suite uses a mock model and sends nothing externally. Note: on the AI Studio free tier, Google may use prompts to improve its products — use sample data or a paid tier for real client data.
- **Safety**: No shell or arbitrary code execution. Client replies and bank narrations are treated as untrusted data (prompt-injection defence); the agent can only propose changes, which the tool validates and the owner confirms.

---

## Future Improvements

- [ ] Live email inbox sync for replies
- [ ] PDF / photo invoice capture
- [ ] Weekly digest and client payment-behaviour insights
- [ ] Optional auto-send for friendly nudges after trust is established
- [ ] WhatsApp channel

---

## License

*This project is contributed under the repository's open-source license.*
