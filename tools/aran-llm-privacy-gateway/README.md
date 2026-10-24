# Aran (அரண்): LLM Privacy Gateway for Indian Documents

> Aran hides Aadhaar, PAN, names, addresses and other personal data **on your machine** before any document reaches a cloud LLM, then puts the real values back into the answer locally.

*Aran* means "fortress" in Tamil. Gemma, running locally, guards the data. Gemini, or any cloud model, only sees what Aran lets through.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Indian fintech, insurance and health teams want to use LLMs on KYC packs, bank statements and lab reports. Sending those documents to a cloud API exposes Aadhaar numbers, PANs, account numbers and patient identities, which is a risk under India's **Digital Personal Data Protection (DPDP) Act**. Generic PII scrubbers miss Indian identifiers and can't read scanned documents.
- **Intended Users**: Developers building LLM features on Indian customer data, and the compliance, risk and platform teams who have to approve them.

### Key Features
- **Indian identifiers with checksum validation**: Aadhaar (Verhoeff), GSTIN (mod-36), cards (Luhn), plus PAN, IFSC, UPI, Indian mobiles, account numbers, PIN codes, UHID/MRN and dates of birth.
- **Local AI for what rules can't catch**: Gemma (via Ollama) finds names, addresses and organisations, and reads **scanned images and scanned PDFs**. Nothing leaves the machine.
- **Every real-world format**: text, digital PDFs, scanned PDFs, PNG/JPG/WebP photos, CSV and Excel (column-aware).
- **Stable tokens**: the same PAN gets the same `<PAN_1>` across every document in a session, so a cloud model can still check that the identity matches across documents without learning what it is.
- **Profiles**: `kyc` and `health` decide per data type whether to **mask** (reversible token), **generalise** (DOB → `[age 35-39]`) or **keep** (IFSC, employer and hospital names). Unknown types are masked by default (fail closed).
- **Fails closed on OCR errors**: if a scan is misread (for example, a dropped PAN letter), Aran still masks anything that looks like an ID instead of letting it through.
- **Restore locally**: the model's answer gets its real values back on your machine, never inside the model's context.
- **DPDP-style audit log**: counts, document hashes and channels for every redaction. It never stores raw values.
- **Four ways to use it**: Python library, CLI, and an **MCP server** that any agent (Gemini CLI, Claude Code, ADK, etc.) can use as its only way to read documents.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+ (managed with `uv`)
- **Agent Framework / Core Library**: Model Context Protocol (MCP Python SDK 2.x), custom detection engine
- **Models**: Gemma 4 12B, run locally through Ollama (configurable). No cloud model is needed for Aran itself.
- **External APIs / Tools**: none. `pypdf`, `pandas`/`openpyxl`, `rich`

---

## Architecture & Data Flow

```
                ┌──────────────────────── your machine ───────────────────────────┐
 document ──▶   │ readers ──▶ rules + checksums ──▶ Gemma (names, addresses, OCR)  │
 (pdf/scan/csv) │                     │                                            │
                │                profile: mask / age_band / keep                   │
                │                     │                                            │
                │      vault (<PAN_1> ↔ real value, 0600)   audit.jsonl (counts)   │
                └─────────────────────┼────────────────────────────────────────────┘
                                      ▼  redacted text only
                              cloud LLM (Gemini, ...)
                                      │  answer with tokens
                ┌─────────────────────▼────────────────────────────────────────────┐
                │ aran.restore(answer, session)  ──▶  answer with real values      │
                └──────────────────────────────────────────────────────────────────┘
```

**MCP security model**, for agents:
- Documents are exposed as opaque IDs (`doc_1`, `doc_2`), because filenames often contain people's names.
- Only files inside `ARAN_DOCS_DIR` can be read; the model can't pass arbitrary paths.
- The vault session is fixed by the host process (`ARAN_SESSION_ID`), not chosen by the model.
- There is **no `restore` tool**: real values can never be pulled back into a model's context.

---

## Prerequisites

- Python 3.11+ and [`uv`](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com) with a vision-capable local model: `ollama pull gemma4:12b` (about 8 GB)
  - Without Ollama you can still use `--no-llm`, which runs the rules only (all ID numbers, but no names or addresses and no scans).
- No API keys.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/aran-llm-privacy-gateway
   ```

2. **Install dependencies:**
   ```bash
   uv sync
   ```

3. **Make sure the local model is available:**
   ```bash
   ollama pull gemma4:12b
   ```

4. **(Optional) Regenerate the synthetic sample documents:**
   ```bash
   uv run python scripts/make_samples.py
   ```

---

## Configuration & Environment Variables

All variables are optional. See `.env.example`.

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `ARAN_LOCAL_MODEL` | No | `gemma4:12b` | Ollama model for names, addresses and OCR |
| `OLLAMA_HOST` | No | `http://localhost:11434` | Ollama endpoint |
| `ARAN_HOME` | No | `~/.aran` | Location of the token vault and audit log (owner-only permissions) |
| `ARAN_DOCS_DIR` | No (MCP only) | `.` | Folder whose documents the MCP server exposes |
| `ARAN_SESSION_ID` | No (MCP only) | random | Vault session chosen by the host, so it can restore answers later |

---

## How to Run

```bash
# What personal data does a document contain, and what would Aran do with it?
uv run aran scan samples/kyc/aadhaar_card.png samples/kyc/salary_slip.txt

# The redacted text: this is all a cloud LLM would ever see
uv run aran redact samples/kyc/bank_statement.pdf --profile kyc

# Health documents use a different policy
uv run aran redact samples/health/lab_report.png --profile health

# Put real values back into a model's answer (local only)
echo "Applicant <PERSON_1> holds PAN <PAN_1>" | uv run aran restore --session <session-id>

# Audit trail and policies
uv run aran audit
uv run aran profiles

# MCP server on stdio, for agents
ARAN_DOCS_DIR=samples/kyc uv run aran mcp
```

**Use it from any MCP client**, for example Claude Code or Gemini CLI:
```json
{
  "mcpServers": {
    "aran": {
      "command": "uv",
      "args": ["run", "--directory", "/abs/path/to/tools/aran-llm-privacy-gateway", "aran", "mcp"],
      "env": { "ARAN_DOCS_DIR": "/abs/path/to/case-documents" }
    }
  }
}
```

**As a library:**
```python
import aran

r = aran.redact_document("samples/kyc/bank_statement.pdf", profile="kyc")
answer = call_your_llm(r.redacted)          # only tokens leave the machine
print(aran.restore(answer, r.session_id))   # real values back, locally
```

For a full agent built on Aran, see [`agents/aran-kyc-underwriter`](../../agents/aran-kyc-underwriter/).

---

## Example Input & Output

All sample documents are **synthetic** and stamped SPECIMEN. The identifiers have valid checksums but belong to no one. `samples/ground_truth.json` lists the planted values; the agent evals use it to prove none of them reached the cloud. It's kept outside `samples/kyc/`, so an agent can never read it.

### Example Input
`samples/kyc/aadhaar_card.png`, a scanned card image read by Gemma locally, and `samples/kyc/salary_slip.txt`:
```bash
uv run aran scan samples/kyc/aadhaar_card.png samples/kyc/salary_slip.txt
```

### Example Output
```
samples/kyc/aadhaar_card.png  (image, profile=kyc)
┏━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┓
┃ Type    ┃ Value (hint)   ┃ Action   ┃ Becomes     ┃ Checksum ┃ Detector ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━┩
│ PERSON  │ K***           │ mask     │ <PERSON_1>  │ -        │ llm      │
│ DOB     │ ******1991     │ age_band │ [age 35-39] │ -        │ rule     │
│ ADDRESS │ N***           │ mask     │ <ADDRESS_1> │ -        │ rule     │
│ PINCODE │ **0038         │ mask     │ <PINCODE_1> │ -        │ rule     │
│ AADHAAR │ **********9624 │ mask     │ <AADHAAR_1> │ valid    │ rule     │
└─────────┴────────────────┴──────────┴─────────────┴──────────┴──────────┘
samples/kyc/salary_slip.txt  (text, profile=kyc)
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┓
┃ Type           ┃ Value (hint)    ┃ Action   ┃ Becomes            ┃ Checksum ┃ Detector ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━┩
│ ORG            │ N***            │ keep     │ (kept)             │ -        │ llm      │
│ GSTIN          │ ***********Q1ZL │ mask     │ <GSTIN_1>          │ valid    │ rule     │
│ PERSON         │ K***            │ mask     │ <PERSON_1>         │ -        │ rule     │
│ PAN            │ ******821M      │ mask     │ <PAN_1>            │ valid    │ rule     │
│ ACCOUNT_NUMBER │ **********7812  │ mask     │ <ACCOUNT_NUMBER_1> │ -        │ rule     │
│ IFSC           │ *******1234     │ keep     │ (kept)             │ -        │ rule     │
│ DOB            │ ******1991      │ age_band │ [age 35-39]        │ -        │ rule     │
└────────────────┴─────────────────┴──────────┴────────────────────┴──────────┴──────────┘
╭──────────────────────────────── Aran ────────────────────────────────╮
│ 12 personal data items found in 2 document(s)                        │
│ 10 hidden or generalised before any cloud call                       │
│ 0 raw values sent to the cloud      session: s_f82714a7f204          │
╰──────────────────────────────────────────────────────────────────────╯
```

Redacted bank statement (`aran redact samples/kyc/bank_statement.pdf`, same session). The cloud model still sees the salary, the EMIs and the bounced payment, but not who the account belongs to:
```
Account Holder: <PERSON_1>
Address: <ADDRESS_1>
A/c No: <ACCOUNT_NUMBER_1>    IFSC: HDFC0001234    Branch: Indiranagar
Registered Mobile: <PHONE_1>    Email: <EMAIL_1>
PAN: <PAN_1>    Period: 01/07/2026 to 30/09/2026
01/07/2026 NEFT CR SALARY NIMBUS ANALYTICS PVT LTD JUL 86,500.00 128,850.00
05/07/2026 UPI/rent/<UPI_1>/<PERSON_2> 22,000.00 92,350.00
25/08/2026 ACH DR BAJAJ FINSERV EMI PL5521 9,800.00 89,910.00
26/08/2026 ACH RETURN BAJAJ FINSERV EMI PL5521 - INSUFFICIENT FUNDS 9,800.00 99,710.00
```

OCR fail-closed in action (`samples/kyc/pan_card.png`). Gemma misread `BQKPR4821M` as `BQPR4821M`, which is no longer a valid PAN, and Aran still masked it:
```
Permanent Account Number Card
<ID_NUMBER_1>
Name
<PERSON_1>
Father's Name
<PERSON_2>
Date of Birth
[age 35-39]
```

Health profile (`samples/health/lab_report.png`). The patient is hidden, and the clinical values are kept. The lab's own landline is also masked: on scans, Aran fails closed and masks number-shaped values even when they aren't personal.
```
KAVERI DIAGNOSTICS (SAMPLE LAB - SPECIMEN)
Jayanagar, Bengaluru | Ph: <ID_NUMBER_1>
Patient Name: <PERSON_1>
UHID: <MEDICAL_ID_1> Date of Birth: [age 55-59]
Mobile: <PHONE_1> Sample Date: 10/10/2026
Referred By: Dr. <PERSON_2>
Address: <ADDRESS_1>
HbA1c 8.2 % H 4.0 - 5.6
Fasting Glucose 168 mg/dL H 70 - 100
```

CSV (`samples/customers.csv`, column-aware, no local model needed):
```
customer_name,mobile,email,pan,aadhaar,city,loan_amount,bank_name
<PERSON_1>,<PHONE_1>,<EMAIL_1>,<PAN_1>,<AADHAAR_1>,Bengaluru,1200000,HDFC Bank
<PERSON_2>,<PHONE_2>,<EMAIL_2>,<PAN_2>,<AADHAAR_2>,Chennai,450000,ICICI Bank
```

---

## Guardrails

Each layer works on its own, so a miss in one doesn't open a hole:

| # | Guardrail | What it stops | Where |
| :--- | :--- | :--- | :--- |
| 1 | **Checksum-validated rules** | Random numbers being masked by mistake, and real IDs being missed | `detectors.py` |
| 2 | **Local model for names, addresses and OCR** | Personal data that no regex can describe; scans never leave the machine | `local_llm.py` |
| 3 | **Label rules as a safety net** | `Patient Name:` / `Address:` values the local model misses (for example, split across OCR lines) | `detectors.py` |
| 4 | **OCR fail-closed** | A misread ID (dropped letter, `0`→`O`) leaking because it no longer matches any format | `detectors.py` (`ocr=True`) |
| 5 | **Fail-closed profiles** | New or unknown data types being sent; anything without a rule is masked | `profiles/` |
| 6 | **Egress guard** | Any text about to leave the machine containing a value already in the vault, or a valid ID that was never redacted | `guard.py` |
| 7 | **MCP hardening** | Path traversal, filename leaks, session switching, and pulling real values back into a model (no restore tool) | `mcp_server.py` |
| 8 | **Audit log with no personal data** | Compliance evidence that itself becomes a liability | `audit.py` |

```python
from aran import guard
leaks = guard.find_leaks(outgoing_text, session_id, profile="kyc")  # [] means safe to send
```

---

## Evaluation Results

`evals/` is a reproducible harness built on a **labelled synthetic corpus**: 6 Indian document templates (KYC form, loan email, bank transactions, support chat, GST invoice, lab report), with known personal data values and known useful values. It measures what matters for a privacy gateway and **exits non-zero if a threshold is breached**, so it can run as a CI gate.

```bash
uv run python evals/run_evals.py               # rules only: fast and deterministic (CI)
uv run python evals/run_evals.py --llm --n 5   # with local Gemma
```

Results from real runs (`evals/results/*.json`):

| Metric | Rules only (840 values) | With Gemma (140 values) | Gate |
| :--- | ---: | ---: | :--- |
| Structured IDs leaked (Aadhaar, PAN, GSTIN, card, phone, email, UPI, account, PIN, UHID, DOB) | **0.0%** | **0.0%** | = 0% |
| All personal data leaked (including names and addresses in free text) | 10.71% | **0.0%** | ≤ 0.5% with the model |
| Useful values kept (amounts, IFSC, dates, lab values, invoice numbers) | 100% | 100% | ≥ 99% |
| Restore round trip exact | 100% | 100% | = 100% |
| OCR-misread IDs still protected | **100%** (20% without the fail-closed guard) | 100% | = 100% |
| Egress guard: false blocks on clean output | 0 | 0 | = 0 |
| Egress guard: re-injected personal data caught | 100% | 100% | = 100% |

What the numbers say:
- **Rules alone protect every structured ID**, but leak 37.5% of names that appear in free text ("please process the loan for Arjun Mehta"). That's why the local model exists, and with it, name leaks dropped to 0 on this corpus.
- **The OCR guard matters.** Without it, 80% of misread IDs would have been sent to the cloud.
- The harness caught two real bugs during development: misread Aadhaar numbers in digit groups getting through, and doctor names with a "Dr." prefix escaping the egress guard. Both are fixed, and both are now covered by the gates.
- **Caveat**: the corpus is synthetic and templated, and the Gemma run is small (30 documents, about 90 s). Real documents will be messier; treat these results as regression gates, not as a guarantee.

---

## How to Test

```bash
# Offline unit tests (no Ollama needed): checksums, overlaps, round-trip restore,
# session consistency, profiles, OCR fail-closed, egress guard, audit has no PII, vault perms,
# and parallel redactions in one session (vault locking)
uv run pytest -q

# Evaluation harness (see above)
uv run python evals/run_evals.py

# End-to-end with the local model
uv run aran scan samples/kyc/* samples/health/* samples/customers.csv
```

---

## Known Limitations

- **The local model can miss things.** Names and addresses that aren't next to a label rely on Gemma. The label-based rules and the fail-closed OCR guard reduce misses but can't rule them out. Review `aran scan` output before using Aran on a new document type.
- **Speed**: tested on an Apple Silicon Mac. One scanned image takes about 15 s to OCR with Gemma 4 12B, and a text page about 5–10 s. Rules-only mode (`--no-llm`) is instant.
- **On scans, Aran deliberately over-masks**: number-shaped and ID-shaped values (for example a lab's landline or a reference code) become `<ID_NUMBER_n>`, because a misread personal ID must not leak. On typed text, only validated or labelled values are masked.
- **Tokens reveal the type of data** (`<PAN_1>`), and kept fields (amounts, employer, IFSC) are still visible to the cloud model by design. Choose or edit profiles to match your purpose.
- **Indian identifiers only** for now (plus email, cards and phone numbers). Passport, voter ID and driving licence numbers are only caught by the OCR guard, not by dedicated rules.
- Handwritten documents and non-Latin scripts (Hindi, Tamil on Aadhaar cards) haven't been evaluated.
- Tested on macOS; Linux should work. **Windows isn't supported** yet, because the vault lock uses `fcntl`.

---

## Security & Privacy Considerations

- **Secrets Handling**: Aran needs no API keys. The vault (`~/.aran/vault/*.json`) maps tokens to real values. It is created with `0600` permissions, locked per session so parallel redactions (agents call tools in parallel) can't lose or reuse tokens, and saved atomically, but it is **not encrypted**. Treat it like the original documents and delete sessions you no longer need.
- **Data Privacy**: all detection, OCR and restoring happen locally (Ollama on `localhost`). The audit log stores only counts, a truncated SHA-256 of each document, and channel names.
- **Safety**: Aran never runs code from documents. The MCP server only reads files inside `ARAN_DOCS_DIR`, hides filenames, and has no restore tool. If no profile rule applies, data is masked.

---

## Future Improvements

- [ ] OpenAI/Gemini-compatible HTTP proxy mode (change `base_url` and every call is protected)
- [ ] Encrypt the vault at rest (OS keychain)
- [ ] Rules for passport, voter ID (EPIC) and driving licence numbers
- [ ] Support for Hindi and Tamil scripts in OCR and name detection
- [ ] A detection benchmark (precision and recall) on a larger synthetic set

---

## License

*This project is contributed under the repository's open-source license (MIT).*
