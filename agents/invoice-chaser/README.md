# Invoice Chaser

> An AI agent that helps freelancers and small agencies get paid on time. It matches bank payments to invoices (including TDS short-payments), drafts reminders in the right tone in English or Hinglish, and queues them for your approval. Every amount and date comes from a deterministic ledger, and nothing is sent without you.

Design docs: [docs/PRODUCT.md](docs/PRODUCT.md) (product spec) · [docs/TECHNICAL_SCOPING.md](docs/TECHNICAL_SCOPING.md) (principles, failure handling, evals)

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Freelancers send invoices and then spend hours chasing payment. They match cryptic bank references (often short-paid because the client deducted TDS) to invoices, remember who to follow up with, and agonise over wording that won't damage the relationship.
- **Intended Users**: Independent freelancers and small agencies (5–20 active clients) who invoice by email and get paid by bank transfer, especially in India.

### Key Features
- **Payment matching with TDS awareness.** The agent reads the payer name in the bank narration. The ledger checks the amount (exact, 10% TDS, partial, overpaid, or several invoices at once) and decides whether the match is applied automatically or waits for your confirmation.
- **Ranked chase list.** Overdue invoices ranked by amount and age, each with a recommended tone (heads-up, gentle nudge, firm reminder, final notice) capped per client.
- **Grounded reminder drafts.** The model writes templates with slots such as `{amount_due}`. The ledger fills them in and rejects any draft where the model typed digits, ₹/Rs/INR, number words ("hazaar", "lakh") or threatening language.
- **English and Hinglish.** Per-client language preference.
- **You stay in control.** Confirming matches, approving or sending reminders and disputing invoices are owner-only CLI actions. The agent's tool server cannot do them.
- **MCP server.** The ledger is a standalone MCP server, so other MCP clients can use it too.
- **Audit trail and invariants.** Every write is logged with who did it and why. Ledger invariants (for example "never settle more than the invoice amount") are checked inside every transaction.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+ (tested on 3.11)
- **Agent Framework / Core Library**: [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) 2.13: a root agent with two single-turn sub-agents. The tools are a **Model Context Protocol (MCP)** server (MCP Python SDK 2.3), consumed through ADK's `McpToolset`.
- **Models**: Gemini via a Google AI Studio API key. Default `gemini-3.5-flash` (ADK's default), configurable with `MODEL_NAME`.
- **External APIs / Tools**: SQLite (local file). No other services.
- **Interface**: `adk web` (chat UI with tool-call traces) and `cli.py` (imports, approvals, headless runs)

---

## Architecture & Data Flow

```
 You ──► cli.py (owner)                         You ──► adk web / cli.py chase
           │ import · confirm matches                    │
           │ approve / edit / skip drafts                ▼
           │ mark sent · dispute            ┌─────────────────────────────┐
           │                                │ invoice_chaser (root agent) │
           │                                │  ├─ payment_matcher         │
           │                                │  └─ reminder_drafter        │
           │                                └──────────────┬──────────────┘
           │                                               │ MCP tool calls (stdio)
           │                                               │ per-agent allow-list
           │                                               ▼
           │                                ┌─────────────────────────────┐
           │                                │ ledger MCP server           │
           │                                │ role fixed to "agent":      │
           │                                │ read · propose · queue only │
           │                                └──────────────┬──────────────┘
           ▼                                               ▼
     ┌──────────────────────────────────────────────────────────────────┐
     │ Ledger (deterministic Python): parsing · matching · ageing ·     │
     │ policy · renderer + number guard · state machines · invariants · │
     │ audit                                       SQLite: data/ledger.db│
     └──────────────────────────────────────────────────────────────────┘
```

**A chase run:** the root agent calls `payment_matcher`. It lists unmatched payments and open invoices, then calls `propose_match` with a name-confidence score, and the ledger decides `AUTO_APPLIED` or `NEEDS_CONFIRMATION`. Next the root agent calls `reminder_drafter`. It reads the chase list, writes slot templates at the recommended tone and language, and calls `queue_reminder`. The ledger re-checks policy, renders the draft, or rejects it with problems to fix. Finally the root agent calls `run_report` and summarises.

**Rules the code enforces:**
- The LLM never computes money or dates and never writes to storage directly.
- Each sub-agent sees only its own tools.
- A `before_tool_callback` blocks out-of-scope tools and stamps a per-request `run_id`, so the model can't forge it.

Full design: [docs/TECHNICAL_SCOPING.md](docs/TECHNICAL_SCOPING.md).

---

## Prerequisites

- **Python 3.10 or newer.** macOS ships 3.9, which is too old. One option is [uv](https://docs.astral.sh/uv/): `uv venv --python 3.11 .venv`
- pip (or uv)
- A **Google AI Studio API key** for running the agent and the live evals (free tier works): https://aistudio.google.com/apikey. The test suite does **not** need a key.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/invoice-chaser
   ```

2. **Create a virtual environment and install dependencies:**
   ```bash
   python3.11 -m venv .venv          # or: uv venv --python 3.11 .venv
   source .venv/bin/activate         # Windows: .venv\Scripts\activate
   pip install -r requirements.txt   # or: uv pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # edit .env and set GOOGLE_API_KEY
   ```

4. **Create the ledger with the demo data:**
   ```bash
   python cli.py init --sample
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | To run the agent / evals | *None* | Google AI Studio API key |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | `FALSE` | Keep `FALSE` for AI Studio |
| `MODEL_NAME` | No | `gemini-3.5-flash` | Gemini model for all three agents |
| `JUDGE_MODEL` | No | `MODEL_NAME` | Model used only by the eval judge |
| `INVOICE_CHASER_DB` | No | `data/ledger.db` | SQLite ledger; relative paths resolve against this folder |
| `INVOICE_CHASER_TODAY` | No | real date | Fixed "today" (`YYYY-MM-DD`). `.env.example` sets `2026-10-24`, the date the sample data is written for |
| `INVOICE_CHASER_TDS_RATES` | No | `0.10` | TDS rates the matcher recognises, comma-separated |
| `INVOICE_CHASER_SENDER_NAME` | No | `Priya` | Name used in `{sender_name}` |
| `INVOICE_CHASER_PAYMENT_DETAILS` | No | `the bank details on the invoice` | Text used in `{payment_details}` |

Only the `INVOICE_CHASER_*` variables are passed to the MCP tool process. Your API key stays in the agent process.

---

## How to Run

```bash
python cli.py status                  # ranked chase list (no key needed)
python cli.py chase                   # agent: match payments + draft reminders
python cli.py ask "who owes me the most?"
python cli.py matches                 # confirm / reject uncertain matches
python cli.py review                  # approve / edit / skip drafts
python cli.py sent 1                  # after you send draft #1 yourself
python cli.py hold INV-2026-004 disputed --reason "client says menu not final"
python cli.py audit --invoice INV-2026-004

adk web .                             # chat UI at http://localhost:8000, pick "invoice_chaser"
python -m ledger.mcp_server           # the ledger as a standalone MCP server (stdio)
```

Your own data: `python cli.py import clients|invoices|payments <file.csv>`. The column formats are in `sample_data/`. Bank statements need `date, narration, ref, credit, debit[, currency]`.

---

## Example Input & Output

These outputs are from genuine runs on the bundled sample data with `INVOICE_CHASER_TODAY=2026-10-24`.

### `python cli.py status` (before any matching)
```
As of 2026-10-24

Invoice       Client                      Outstanding   Overdue  Tone           Next step
INV-2026-005  Kite Learning                   ₹75,000       44d  final notice   can draft reminder
INV-2026-001  Acme Design Pvt Ltd             ₹50,000       54d  firm reminder  can draft reminder
INV-2026-010  Acme Design Pvt Ltd             ₹50,000       24d  firm reminder  can draft reminder
INV-2026-002  Bloom Organics                  ₹30,000       35d  gentle nudge   can draft reminder
INV-2026-012  GreenLeaf Foods                 ₹28,000       23d  firm reminder  can draft reminder
INV-2026-004  Chai Point Cafe Pvt Ltd         ₹18,000       19d  firm reminder  can draft reminder
INV-2026-007  Pixel Forge Studios             ₹40,000        4d  gentle nudge   can draft reminder
INV-2026-006  Sharma & Sons Traders           ₹22,000        9d  firm reminder  can draft reminder
INV-2026-003  Northwind Analytics Inc          $1,200       14d  firm reminder  can draft reminder
INV-2026-008  Pixel Forge Studios             ₹15,000    due 2d  heads-up       can draft reminder

7 unmatched payment(s) · 0 match(es) to confirm (cli.py matches) · 0 draft(s) to review (cli.py review)
```
Bloom Organics is capped at "gentle nudge" by its `gentle` flag. Kite Learning is the only client that has opted in to final notices.

### `python cli.py matches` (owner confirming what the agent was unsure about)
```
#1  2026-10-14  ₹30,000  "UPI/CR/628745123456/CHAIPOINT CAFE/YESB/payment"
   → INV-2026-004, INV-2026-011   (EXACT, name confidence 0.95)
   agent's reason: CHAIPOINT CAFE = Chai Point Cafe
   INV-2026-004: Chai Point Cafe Pvt Ltd, outstanding ₹18,000
   INV-2026-011: Chai Point Cafe Pvt Ltd, outstanding ₹12,000
   ⚠ the amount also fits: INV-2026-002
   [c]onfirm  [r]eject  [s]kip >
```
A payment covering several invoices always needs your confirmation. Here the ledger also warns that ₹30,000 exactly matches a *different* client's invoice.

### Ledger rejecting a draft where the model typed a number
```json
{"ok": false, "error_code": "RENDER_REJECTED",
 "problems": ["body: must include {invoice_no}", "body: must include {amount_due}",
              "body: contains digits outside slots (use {amount_due}, {due_date} etc.)"]}
```

### `python cli.py chase` (live Gemini run)
*Pending: this will be filled in from a genuine run with a Gemini key. Until then, nothing here is invented.*

---

## How to Test

**Offline (no API key):** 196 tests in about 4 seconds:
```bash
python -m pytest -q
```
- **Ledger:** parsing, imports, matching (TDS, partial, overpaid, several invoices, ambiguity, currency), ageing and tone, policy, the renderer's number guard, state machines (all transitions), invariants including rollback, permissions, audit.
- **Agent flows:** the real ADK runner and the real MCP server subprocess, driven by a **scripted mock model**. Covers a full chase run, render rejection reaching the model, a sub-agent calling a tool outside its allow-list, `run_id` forgery, and a prompt injection in a bank narration.
- **Eval harness:** scoring logic and plumbing.

**Live evals (needs `GOOGLE_API_KEY`):**
```bash
python -m evals.run_evals                  # all suites; add --repeat 3 to measure variance
python -m evals.run_evals --suite matcher  # matcher | drafter | scenarios
```
| Suite | What it measures | Pass threshold |
|---|---|---|
| matcher | 20 labelled bank lines (`evals/data/matcher_cases.json`): TDS, abbreviations, multi-invoice, partial, foreign fees, similar-name trap, prompt injection, bank interest | auto-apply precision 100%, no wrong auto-applies, ≥ 85% of cases passed |
| drafter | Every eligible chase item: rule checks (tone, language, invoice and amount present, length) plus a Gemini judge (tone fit, politeness, clarity, language, 1–5) | 100% coverage and rules; judge mean ≥ 4, no score < 3 |
| scenarios | Full chase run on sample data (expected final ledger state, injection ignored, every ₹ amount in the summary appears in a tool result) and a same-day re-run (no duplicates) | all checks |

Reports are written to `evals/results/<timestamp>.md` (git-ignored). Scores come from the ledger state after each run, not from what the agent claims.

---

## Known Limitations

- **Live behaviour not yet measured.** The agent prompts have not yet been run against Gemini; run the live evals to get real numbers. Offline tests verify the wiring and the deterministic guarantees, not the quality of the model's judgement.
- Drafts only. Nothing is ever sent; you send approved drafts yourself.
- No live bank or inbox integration; statements are imported as CSV. Reply handling (promises to pay, disputes) is designed in the docs but not built.
- TDS is recognised only before any partial payment, and only at configured rates.
- Foreign-currency payments match only invoices in the same currency; fee-deducted wires always need confirmation.
- The Hinglish rule check is a keyword heuristic; tone and language quality are judged by an LLM that hasn't been calibrated against human ratings.
- Each agent run starts its own MCP subprocess per agent (three in a chase run). Fine locally; not designed for multi-user hosting.
- Free-tier Gemini rate limits can slow or fail eval runs. Failed cases are reported as failed, never skipped.
- Tested on macOS with Python 3.11. Linux should work; Windows untested.

---

## Security & Privacy Considerations

- **Secrets Handling**: The API key is loaded from a local `.env` (git-ignored); only `.env.example` is committed. The key is never passed to the MCP tool process.
- **Data Privacy**: Client names, invoice numbers, amounts and bank narrations are sent to Google's Gemini API during agent runs. Bank account numbers are not stored or sent. On the AI Studio free tier Google may use prompts to improve its products, so use the sample data or a paid tier for real client data. The ledger, sessions (`invoice_chaser/.adk/`) and eval results stay local and are git-ignored.
- **Safety**:
  - No shell or code execution, and the agent cannot read arbitrary files (imports are owner-only).
  - Bank narrations are labelled untrusted in the tools and prompts. Even if the model obeys an injected instruction, the ledger only accepts an amount-checked proposal for one client, so nothing is marked paid without matching money.
  - `adk web` is a local development server with no authentication; don't expose it to a network.

---

## Future Improvements

- [ ] Reply handling: paste a client reply, then track promises to pay and disputes (designed in `docs/`)
- [ ] Calibrate the eval judge against human-rated drafts
- [ ] Email export (`.eml`) for approved drafts
- [ ] Live bank statement and inbox integrations
- [ ] PDF/photo invoice capture
- [ ] Weekly digest and client payment-behaviour insights

---

## License

*This project is contributed under the repository's open-source license.*
