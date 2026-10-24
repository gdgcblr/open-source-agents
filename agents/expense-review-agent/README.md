# Expense Review Agent

> Turn read-only Gmail messages and personal Keep exports into evidence-backed financial proposals for human review.

## Overview

This Python agent is for people whose transaction records are scattered
across emails and notes. It collects source text, asks Google's Gemini API to extract
structured transactions, applies deterministic guardrails, and stages a review
queue. Nothing enters the monthly ledger until explicitly approved by a person.

It separates spending, lending, borrowing, repayments received, repayments paid,
income, and transfers. The monthly dashboard counts only approved INR entries;
loan proceeds are not treated as earnings and lending is not treated as spending.
Monthly cashflow includes borrowing, lending, and repayments with their proper
cash directions; transfers between the user's own accounts are excluded.

## Why Use This Agent?

Financial records often mix several different events: a purchase receipt, money
lent to a friend, a loan received, and a repayment. Treating every debit as an
expense or every credit as income produces misleading monthly totals. Copying
these records into a spreadsheet also loses the original context behind an entry.

This agent reduces that manual sorting while keeping the decision with you:

- Collect relevant emails and exported notes into one local review queue.
- Suggest transaction fields and tags from unstructured text using Gemini.
- Preserve the original source, verbatim evidence, and a short classification reason.
- Distinguish purchases from loans, repayments, income, and internal transfers.
- Require human approval before a proposal affects the ledger.

Gemini proposes an interpretation; Python validates it and the person reviewing
the source decides whether it should count. This is useful when you want assisted
bookkeeping without giving a model authority to approve financial records.

## Where Is It Useful?

| Situation | How the agent helps |
| --- | --- |
| Personal monthly expense review | Combines receipt emails and transaction notes, then totals approved spending by category. |
| Informal lending and borrowing | Keeps money lent, loans received, and repayments separate from normal purchases and earnings. |
| Shared expenses or reimbursements | Preserves who a note mentions and why a transaction was proposed so you can verify its direction. |
| Learning or prototyping financial AI workflows | Demonstrates structured extraction, source evidence, deterministic guardrails, and a human approval gate. |

It is not a bank connection, payment tool, tax-reporting system, or replacement
for accounting software. It does not calculate outstanding loan balances or
automatically match repayments to individual loans. Use it only where sending
the selected financial source text to Google's Gemini API is acceptable.

## Technical Stack

- Python 3.11+, Pydantic validation, HTTPX, and SQLite.
- Read-only Gmail through Google's official OAuth and Gmail clients.
- Personal Google Keep through exported Takeout JSON, not password scraping.
- Gemini's HTTPS structured-output API; default model `gemini-3.8-flash`,
  configurable through `GEMINI_MODEL` or `--model`. No Ollama installation is needed.
- No ADK dependency or model-controlled write tools. This is a bounded
  collection/extraction/review workflow, not an unrestricted autonomous agent.

## Architecture & Data Flow

```text
Gmail (read-only) / Keep JSON -> raw source notes -> Gemini API extraction (Google cloud)
  -> schema validation -> evidence/amount/currency checks -> pending candidates
  -> human correction + approval/rejection -> audited ledger -> monthly totals
```

Raw notes and original proposals are retained alongside the current proposal,
evidence, classification reason, confidence, review flags, and decision audit.
Reimporting identical source notes is idempotent. Low-confidence proposals remain
flagged; unsupported currencies, unknown direction, and unsupported evidence or
amount block approval. Same date/amount/currency as an approved entry requires
explicit confirmation that the candidate is a distinct transaction.

## Prerequisites

Python 3.11+ with pip and venv. For real extraction, create a Gemini API key at
https://aistudio.google.com/apikey and enable access/billing as required by your
project. Review https://ai.google.dev/gemini-api/docs/pricing and the API's data
processing terms before submitting financial information. Internet access to
`generativelanguage.googleapis.com` is required. For Gmail,
enable Gmail API in a Google Cloud project, configure OAuth consent (add your
account as a test user if applicable), and create a Desktop OAuth client.
Download its credentials JSON outside this repository. Personal Keep requires
an export from https://takeout.google.com with Keep selected.

## Installation & Setup

Clone the repository if you do not already have it:

```bash
git clone https://github.com/gdgcblr/open-source-agents.git
cd open-source-agents
```

From the repository root, install only this agent:

```bash
cd agents/expense-review-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
expense-review --help
```

Set the key privately in your shell. In macOS's default zsh, this prompts without
echoing the key or putting its value into your command history:

```zsh
read -rs "GEMINI_API_KEY?New Gemini API key: "
export GEMINI_API_KEY
printf '\n'
```

Use a newly generated key if a previous one was exposed in chat, logs, or Git.
Restrict it to the intended API/project and rotate it when necessary. Do not
paste it into source code or frontend environment variables. For hosting, use
your platform's server-side secret manager instead of an interactive prompt.
On Windows, use `.venv\Scripts\Activate.ps1` for activation. Verified on macOS
with Python 3.14; other platforms and the minimum runtime are not verified.

The `expense-review` command is installed by this package. You do not need the
research assistant, Node.js, a frontend, or the private companion backend to run
the agent. Installation and offline tests do not require an API key or Google login.

## Configuration & Environment Variables

`EXPENSE_DATA_DIR` optionally selects the private data directory; otherwise data
lives at `~/.local/share/expense-review`. The CLI's global `--data-dir` overrides
it. The directory contains `ledger.sqlite3` and, after OAuth, `gmail-token.json`.
`GEMINI_API_KEY` is required only for reasoning, not importing, listing, or
reviewing notes. `GEMINI_MODEL` selects the default model; the reasoning command's
`--model` flag overrides it. Use a bare Gemini model ID, not a URL or `models/`
prefix. The default follows Google's documented Flash example; actual model
availability, quotas, and billing depend on your project and are not live-verified.
The key is sent in an HTTPS header, never a query string, and is not stored in
the ledger. `.env` files are not automatically loaded.

## How to Run

### 1. Choose Your Source

You can start with Gmail, a Keep export, or both. They are independent import
routes; you do not need to connect Gmail to use Keep.

For Gmail, enable Gmail API in your Google Cloud project, configure the OAuth
consent screen, add your account as a test user if the app is in testing, and
create an OAuth client with application type **Desktop app**. Save its downloaded
JSON outside this repository. Then authorize your account locally:

```bash
expense-review auth-gmail --credentials /absolute/private/path/client.json
expense-review fetch-gmail --limit 20
```

The authorization command opens Google's browser consent page. After you approve
read-only access, it saves a private token in the configured data directory.
The default search looks for transaction-related messages from the last 45 days;
use `expense-review fetch-gmail --query "YOUR_GMAIL_QUERY" --limit 20` to change it.

For personal Google Keep, request a Keep export at https://takeout.google.com,
download and extract it locally, then import one exported note JSON:

```bash
expense-review import-keep /absolute/path/to/Takeout/Keep/example.json
```

The browser consent requests `gmail.readonly`; no email is modified or sent.
Google Keep's official API targets enterprise administration; this project does
not claim live personal Keep sync. Import one exported note JSON at a time, or
a JSON array / `{"notes": [...]}` containing up to 100 note objects. A note can
have `title`, `textContent`, and `listContent` checklist entries.

### 2. Ask Gemini to Propose Transactions

Set `GEMINI_API_KEY` privately as described above, then run:

```bash
expense-review reason
expense-review list
```

Each reasoning run processes at most 20 queued or errored notes. Run it again for
remaining notes. To choose another supported model, use
`expense-review reason --model YOUR_GEMINI_MODEL_ID`. Model access depends on
your Google project. The agent does not execute commands or approve transactions
on behalf of Gemini.

`list` returns JSON containing source notes, proposals, flags, and the review
audit. A proposal includes date, amount, currency, direction, category,
counterparty, evidence, confidence, and the reason it was suggested. A failed
request or invalid model response leaves an error on the source note instead of
silently counting a transaction.

### 3. Review Before Counting

Inspect the candidate's original source, amount, date, direction, category, and
flags. Replace `CANDIDATE_ID` below with its `id` from `list`; write your own
review note explaining the decision:

```bash
expense-review review CANDIDATE_ID --action approved --note "Matched to the original transaction source."
```

To exclude an incorrect or irrelevant proposal:

```bash
expense-review review CANDIDATE_ID --action rejected --note "The source does not support this transaction."
```

Approval is blocked when required evidence, amount, direction, or INR currency
checks fail. A low-confidence flag still needs careful human review. Rejection
does not require resolving the proposal's blocking flags.

### 4. Read the Approved Monthly Ledger

```bash
expense-review monthly 2026-10
```

Replace `2026-10` with the month you want in `YYYY-MM` format. The JSON output
contains approved totals per transaction kind, spending categories, the approved
entry count, and net cashflow. Pending and rejected candidates never count.

Use `--action rejected` to exclude a candidate permanently. If a duplicate warning
is raised, verify the source and supply `--confirm-distinct` only for genuinely
different transactions. Corrections are available through the Python `Ledger.review`
API; the CLI only reviews existing proposals. The optional companion dashboard
and its Python backend are deliberately outside this repository.

To keep a run's data separate, pass the global data-directory option **before**
the subcommand and use the same directory for each step:

```bash
expense-review --data-dir /absolute/private/path/expense-data list
expense-review --data-dir /absolute/private/path/expense-data monthly 2026-10
```

## Example Input & Output

Offline checks use this explicitly synthetic note, not private financial data:

```text
On 2026-10-20 I paid INR 250 for lunch.
```

A fixture proposes an INR 250 spending entry with category Food and verbatim
evidence. The verified ledger behavior is zero approved entries before review,
one approved entry after review, spending total `250`, and cashflow `-250`.
This verifies bookkeeping, not actual Gemini extraction quality; no live-model
financial result is presented as verified.

## How to Test

```bash
python -m unittest discover -s tests -v
python -m pip check
```

Offline checks cover approval gating, source/amount guardrails, duplicate review,
idempotent imports, loan-direction totals, source parsing, schema failures,
Gemini HTTPS request shape, missing keys, blocked/truncated responses, rate
limits, and credential-safe error handling. HTTP responses are mocked using
dummy credentials; tests do not contact Gemini or send real financial data.
Real Gmail access and live Gemini extraction require local setup and consent;
they are not exercised by the offline checks.

## Known Limitations

- INR only; no FX conversion, bank reconciliation, payment initiation, or loan
  account balances. Repayments are classified but not matched to specific loans.
- Dates, counterparties, categories, completeness, and factual meaning still
  require human verification. Verbatim evidence is not proof a note is truthful.
- Takeout JSON only for Keep; no attachments, PDF parsing, or continuous sync.
- Imports are capped at 100 notes, Gmail at 50 fetched messages, and reasoning
  at 20 notes with a 90-second HTTP timeout and 3,000-token output cap per note.
- Gemini usage can incur charges and is subject to model/project availability,
  quotas, rate limits, network access, and Google's safety filters. Reasoning
  sends raw note/email content to Google; it is no longer local-only processing.
  Requests are not automatically retried. Incomplete or blocked outputs are
  rejected instead of staging potentially truncated transactions.
- Gmail queries can miss relevant messages; model output can be incomplete or
  wrong. Schema failures remain visible as note errors and may be retried.
- Dependencies are range-constrained, not fully locked; one-user local storage
  is not a multi-user finance service. There is no encryption-at-rest layer.

## Security & Privacy Considerations

Emails and notes are sensitive. The ledger stores original text in plaintext;
protect its directory, disk, and backups. Gmail OAuth tokens are written with
owner-only file permissions. Never commit credentials, tokens, exports, local
databases, or actual financial examples. Gmail uses Google's API; reasoning sends
the complete selected source note (including its metadata and text) to Google's
Gemini API over HTTPS. Review https://ai.google.dev/gemini-api/terms, your plan's
data-handling rules, and any organizational restrictions before using private
financial information. The application does not promise local-only inference or
zero provider retention. API keys stay on the server and are not returned by the
API, embedded in request URLs, or saved in source notes. Revoke exposed keys and
never commit real values in `.env.example`.

Source text is untrusted and can include prompt injection. Instructions and
structured output reduce risk but are not a security boundary. The model cannot
approve entries, send mail, access arbitrary files, or execute commands. Human
review and deterministic approval checks are the authoritative write gate.
This is organizational tooling, not financial advice or a certified accounting system.

## Future Improvements

Stronger duplicate matching, configurable evidence checks, review reversal with
audit trails, encrypted storage, loan matching, and optional enterprise Keep integration.

## License

Contributed under the parent repository's MIT license.