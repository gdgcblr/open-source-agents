# TraceTriage — Evidence-First Incident Investigation Agent

> A Google ADK agent that interprets application logs using read-only, privacy-conscious diagnostic tools and produces evidence-linked incident hypotheses.

## Overview

### Problem Statement & Intended Users

Developers, SREs, and incident responders often need to triage noisy service logs under time pressure. Pure LLM diagnosis can invent failures and line numbers. TraceTriage combines deterministic log pattern extraction with an optional conversational ADK agent, grounding suggestions in real evidence from the input.

### Key Features

- **Evidence-linked diagnosis:** Detects database pool exhaustion, timeouts, memory pressure, DNS errors, TLS failures, auth errors, and more. Reports actual log line numbers.
- **Incident timeline:** Lists the first occurrence of each recognized signal in log order.
- **Tool-using AI:** Google ADK agent has three custom Python tools: pasted text triage, allowlisted-file triage, and safe incident runbooks.
- **Private offline fallback:** Deterministic CLI and tests run without any API key or third-party dependencies.
- **Safety:** Read-only tools, 1 MB/5000-line limits, best-effort secret redaction, and file path containment.

## Technical Stack

- **Language & Runtime:** Python 3.11+
- **Agent Framework:** Google Agent Development Kit (ADK)
- **Model:** Google Gemini, configurable using `MODEL_NAME` (default: `gemini-2.5-flash`)
- **Other libraries:** `python-dotenv` for local configuration
- **External services:** Gemini API only for interactive ADK mode; **no external calls** in offline CLI mode

## Architecture & Data Flow

```text
                  +---------------------+
                  | Pasted logs / .log  |
                  +----------+----------+
                             |
            +----------------+-----------------+
            |                                  |
    Offline Python CLI                  Google ADK Agent
            |                                  |
            |                         Tool-call selection
            |                           /      |      \
            |                     text tool  file tool  runbook
            |                           \      |      /
            +---------------------------+------+---+
                                                |
                                  Deterministic signal engine
                                  - pattern and severity matching
                                  - line number evidence
                                  - timeline and ranked signals
                                  - best-effort redaction
                                                |
                                  Structured evidence (JSON)
                                     /                 \
                             Offline report      Gemini explanation
                                                  (hypotheses only)
```

All reasoning and runbook suggestions require user verification. No automatic fixes or infrastructure changes are executed.

## Prerequisites

- Python 3.11+ and pip
- Google AI Studio API key **only if using interactive ADK mode**: https://aistudio.google.com/app/apikey
- A terminal, optionally VS Code

## Installation & Setup

From the upstream repository root, navigate into this self-contained contribution:

```bash
cd agents/log-evidence-triage-agent
python -m venv .venv
```

Activate the virtual environment:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# Linux/macOS
source .venv/bin/activate
```

For **offline CLI/tests**, installation is not necessary. For **Google ADK**:

```bash
python -m pip install -r requirements.txt
```

Copy environment placeholders and supply your own API key for interactive mode:

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

```bash
# Linux/macOS
cp .env.example .env
```

Change `GOOGLE_API_KEY=...` in `.env`. **Never commit `.env`.**

## Configuration & Environment Variables

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `GOOGLE_API_KEY` | Interactive ADK only | unset | Gemini API key from AI Studio |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | `FALSE` | Use Gemini Developer API rather than Vertex AI |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Gemini model accessible to your key |
| `TRIAGE_LOG_DIR` | No | project's `samples/` folder | The **only** directory from which the ADK file tool will read files |

## How to Run

### 1. Fastest demo: offline mode (no key needed)

From `agents/log-evidence-triage-agent/`:

```bash
python -m incident_triage.cli --file samples/spring-boot-incident.log
```

Get machine-readable evidence:

```bash
python -m incident_triage.cli --file samples/spring-boot-incident.log --format json
```

Analyze a short pasted error:

```bash
python -m incident_triage.cli --text "ERROR java.lang.OutOfMemoryError: Java heap space"
```

### 2. AI agent via Google ADK

Install dependencies, supply your key, and execute from the project root:

```bash
adk run incident_triage
```

Alternatively use the web demo (open `http://localhost:8000` and choose `incident_triage`):

```bash
adk web .
```

A good first prompt:

> Investigate the file `spring-boot-incident.log`. What probably triggered the outage, what are downstream symptoms, and which exact lines support your hypothesis?

A second prompt:

> Give me a safe runbook for `database_pool_exhaustion`. What should I check first?

For your own approved logs, put a copy in `samples/` or set `TRIAGE_LOG_DIR` to a dedicated directory. The ADK agent can read only inside that directory. **Do not use sensitive production logs with a hosted model without company authorization.**

## Example Input & Output

### Example Input

The included `samples/spring-boot-incident.log` has realistic (synthetic) Spring Boot/Hikari connection pool saturation followed by request timeouts and 503s.

### Example Output

Running the offline CLI against the sample produces an evidence-based report, including:

```text
=== TraceTriage | Evidence-first incident report ===
Log lines: 10 | Severity: error
Hypothesis: The application appears unable to acquire database connections from its pool.
Verification: Unverified hypothesis; requires investigation

Evidence:
  - Database connection pool exhaustion (3 matching lines)
      L4: ... HikariPool-1 - Connection is not available, request timed out after 30000ms
      L5: ... SQLException: connection pool exhausted for JDBC connection
  - Downstream request timeout (1 matching lines)
      L6: ... Read timed out calling inventory-api /reservations

Suggested checks:
  - Inspect active/idle/pending database pool metrics.
  - Check for slow queries, long transactions, or leaked connections.
  - Review DB maximum connections and recent load changes before increasing pool size.
```

Line excerpts are shortened here for readability; the live output preserves actual line text with best-effort redaction. The sample logs are fabricated; the output is a hypothesis, not verified causality.

## How to Test

Using just Python 3.11+ (no API key):

```bash
python -m unittest discover -s tests -v
```

Check output manually using both `--format text` and `--format json`. For AI mode, verify tool calls in the ADK web developer interface and ensure it cites actual sample lines and distinguishes root causes from symptoms.

## Known Limitations

- Regular-expression signals are **heuristics**, not proof of root cause or full causal tracing. Unrecognized error patterns can be missed.
- ADK responses are probabilistic and depend on model access, network connectivity, and free-tier quota/rate limits.
- The offline engine processes up to 1 MB and 5000 lines; not suited to huge distributed log archives.
- Timestamps are surfaced as text but not normalized across services or time zones.
- Secret redaction is best-effort, not comprehensive DLP. Sensitive logs should not be sent to a hosted LLM without authorization.
- Synthetic sample only; no live production integrations or automatic remediations.

## Security & Privacy Considerations

- API keys are read from an ignored `.env` file; `.env.example` contains placeholders only.
- Offline mode never transmits input data. Interactive ADK uses the configured Gemini service, which receives prompts and tool results with limited, best-effort-redacted excerpts. Review the input before submission.
- AI file-tool access is restricted to `TRIAGE_LOG_DIR` (default: `samples/`), rejecting `../` traversal and other paths resolving outside the approved directory.
- The agent makes no writes to input files and never runs commands on user systems.
- File sizes and returned evidence count are bounded to reduce accidental disclosure and runaway context use.

## Future Improvements

- Detect correlated distributed trace IDs and combine multiple service logs.
- Optional local-model support through Ollama or Gemma.
- Export an incident report to Markdown or JSON with human review.
- Add richer detectors with pluggable rule packs and sanitized private-data test fixtures.

## License

Contributed under the parent repository's MIT License.
