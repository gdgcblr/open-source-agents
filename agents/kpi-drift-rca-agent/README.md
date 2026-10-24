# KPI Drift RCA Agent

> An enterprise-grade Multi-Agent Root Cause Analysis system for analytics engineers and BI teams — diagnoses metric drift without hallucinated math by pairing deterministic Pandas variance decomposition with Gemini diagnostic reasoning, and dispatches assigned operational incident tickets to cross-functional leads.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: When a critical business KPI (conversions, revenue, DAU) unexpectedly drops, analytics teams spend hours manually slicing dimensional cubes to isolate which cohort drove the change. LLMs alone cannot reliably compute multi-dimensional variance decomposition without arithmetic hallucinations, nor do single-prompt agents translate statistical anomalies into actionable operational incident response plans.
- **Intended Users**: Analytics engineers, BI analysts, data scientists, Growth leads, DevOps engineers, and on-call incident response teams who need trustworthy metric triage with immediate operational dispatch.

### Key Features
- **Deterministic-First Architecture**: 100% of the math is computed by Pandas — exact cohort deltas, percentage contributions, and optional conversion-rate decomposition. The LLM never touches arithmetic.
- **Multi-Agent Stakeholder Dispatch Sub-Agent**: Modular secondary agent (`stakeholder_dispatch.py`) that maps isolated culprit cohorts and diagnostic hypotheses into prioritized (P0/P1/P2), SLA-bound operational action tickets assigned to Engineering/DevOps, Growth/Paid Media, and Regional Managers.
- **Dual-Metric & Rate Decomposition**: Decomposes both absolute volume drift (e.g., conversion count drop) and conversion rate drift (e.g., CR% = conversions / sessions) when a secondary metric is available.
- **ASCII Metric Waterfall Visualization**: Terminal-rendered visual waterfall and cohort variance breakdown for instant, intuitive anomaly inspection.
- **Synthetic Sample Dataset Generator CLI**: Synthesizes multi-dimensional mock datasets with configurable drift profiles (`checkout_dropoff`, `payment_gateway_failure`, `mobile_release_regression`, `ad_campaign_fatigue`).
- **Flexible Export Formats**: Exports comprehensive markdown reports (`report.md`) or machine-readable JSON (`--format json`) for integration with PagerDuty, Slack bots, or automated alerting pipelines.
- **Zero-Regression Offline Mode**: Works out of the box with zero flags (`python main.py`), gracefully falling back to deterministic domain rules if `GEMINI_API_KEY` is not configured.
- **Automated Test Suite**: Includes a dedicated `test_agent.py` suite covering decomposition math, dual-metric rates, guardrails, dispatch tickets, and data synthesis.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Core Libraries**: Pandas (deterministic decomposition), argparse (CLI)
- **Model Provider**: Google Gemini via official `google-genai` SDK
- **Models**: `gemini-2.5-flash` (primary), `gemini-3.5-flash-lite` / `gemini-flash-latest` (fallbacks)
- **Architecture**: Multi-agent collaborative pipeline (Deterministic Harness + Reasoning Engine + Stakeholder Dispatch Sub-Agent)
- **Testing**: Python `unittest` standard library (`test_agent.py`)
- **Environment**: `python-dotenv` for secrets management

---

## Multi-Agent Architecture & Data Flow

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                   KPI Drift RCA Multi-Agent Architecture                         │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   [baseline.csv]                                                                 │
│   [current.csv]  ─────┐                                                          │
│                       ▼                                                          │
│   ┌──────────────────────────────────────────────────────────────────────────┐   │
│   │  AGENT 1: Deterministic Mathematical Harness (Pandas)                   │   │
│   │                                                                          │   │
│   │  • Cohort-level Δ = Current - Base (Zero Hallucinations)                 │   │
│   │  • % contribution to total variance                                      │   │
│   │  • Dual-metric Conversion Rate (CR%) decomposition                       │   │
│   │  • ASCII Metric Waterfall & Variance Bar Chart                           │   │
│   └─────────────────────────────────────┬────────────────────────────────────┘   │
│                                         │ Verified Math Facts                    │
│                                         ▼                                        │
│   ┌──────────────────────────────────────────────────────────────────────────┐   │
│   │  AGENT 2: Diagnostic Reasoning Engine (Gemini)                           │   │
│   │                                                                          │   │
│   │  • Executive impact summary                                              │   │
│   │  • Primary anomaly cohort isolation                                      │   │
│   │  • Plausible technical & business hypotheses                             │   │
│   │  • Targeted triage SQL queries & telemetry log commands                  │   │
│   └─────────────────────────────────────┬────────────────────────────────────┘   │
│                                         │ Isolated Culprit + Hypotheses          │
│                                         ▼                                        │
│   ┌──────────────────────────────────────────────────────────────────────────┐   │
│   │  AGENT 3: Stakeholder Action Dispatch Sub-Agent (--dispatch)             │   │
│   │                                                                          │   │
│   │  • Engineering / DevOps Lead : Rollbacks, CDN, API error tracing (P0/2h) │   │
│   │  • Growth / Paid Media Lead  : Bid caps, UTM audits, pixel health (P1/4h)│   │
│   │  • Regional / Geo Manager    : Local gateway status, 3DS banking (P1/4h) │   │
│   └─────────────────────────────────────┬────────────────────────────────────┘   │
│                                         │                                        │
│                                         ▼                                        │
│   ┌──────────────────────────────────────────────────────────────────────────┐   │
│   │  OUTPUT PIPELINE                                                         │   │
│   │  • Rich Terminal Console output with ASCII waterfall                     │   │
│   │  • Executive Markdown Report (report.md)                                 │   │
│   │  • Structured JSON Export (--format json)                                │   │
│   └──────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Step-by-step flow:**
1. **CSV Ingestion & Validation** — Loads baseline and current period CSVs; verifies file-size limits, row count limits, and required column schemas.
2. **Deterministic Decomposition** — Pandas groups by dimensions, calculates exact cohort deltas, percentage contributions, and conversion rate drift.
3. **ASCII Waterfall Rendering** — Renders an intuitive visual cohort waterfall chart directly to the terminal.
4. **Diagnostic Reasoning** — Gemini (or built-in deterministic reasoning engine) generates hypotheses and targeted triage SQL queries.
5. **Stakeholder Action Dispatch (Optional via `--dispatch`)** — The modular sub-agent maps findings into role-assigned operational tickets with priorities and SLAs.
6. **Report Export** — Formats and writes the consolidated output to Markdown or JSON with sensitive path protection.

---

## Directory Structure

```text
agents/kpi-drift-rca-agent/
├── data/
│   ├── baseline.csv            # Baseline period cohort data (mock)
│   └── current.csv             # Current period cohort data (mock)
├── .env.example                # Template — GEMINI_API_KEY placeholder only
├── .gitignore                  # Ignores .env, report.md, __pycache__/, .venv/
├── main.py                     # Agent entry point (harness + reasoning + CLI)
├── README.md                   # Comprehensive documentation
├── requirements.txt            # Minimal Python dependencies (3 packages)
├── stakeholder_dispatch.py     # Modular Multi-Agent Stakeholder Dispatch sub-agent
└── test_agent.py               # Automated unit test suite (10 test cases)
```

---

## Prerequisites

Before running this project, ensure you have:
- **Python 3.10+** installed ([python.org](https://www.python.org/downloads/))
- **pip** package manager (bundled with Python)
- A **Gemini API Key** from [Google AI Studio](https://aistudio.google.com/apikey) *(optional: agent includes built-in offline deterministic reasoning mode)*

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/kpi-drift-rca-agent
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv

   # Windows (PowerShell):
   .\.venv\Scripts\Activate.ps1

   # Linux / macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your API key (optional for live Gemini reasoning):**

   Copy the example file and add your key:
   ```bash
   cp .env.example .env
   # Then edit .env and replace the placeholder with your actual key
   ```

   Or set it directly in your terminal:
   ```bash
   # Windows (PowerShell):
   $env:GEMINI_API_KEY="your_gemini_api_key_here"

   # Linux / macOS:
   export GEMINI_API_KEY="your_gemini_api_key_here"
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
|:---|:---|:---|:---|
| `GEMINI_API_KEY` | Optional | *None* | API key for Google Gemini. If not set, agent runs in offline deterministic diagnostic mode. |

---

## How to Run

### Quickstart (Zero-Flag Execution)
Runs on bundled mock data with deterministic decomposition, ASCII waterfall, and executive RCA report:
```bash
python main.py
```

### Multi-Agent Stakeholder Dispatch
Activate the Stakeholder Dispatch Sub-Agent to generate assigned incident response tickets:
```bash
python main.py --dispatch
```

### Synthetic Dataset Generator CLI
Synthesize configurable drift scenarios on demand:
```bash
# List available scenarios
python main.py --generate-sample list

# Synthesize a payment gateway failure scenario and analyze it immediately
python main.py --generate-sample payment_gateway_failure --dispatch

# Synthesize mobile release regression
python main.py --generate-sample mobile_release_regression
```

### Structured JSON Output
Export machine-readable JSON for integration into incident bots (PagerDuty, Slack):
```bash
python main.py --dispatch --format json --output-report incident_payload.json
```

### Custom Dataset Run
```bash
python main.py \
  --baseline data/baseline.csv \
  --current data/current.csv \
  --metric conversions \
  --secondary-metric sessions \
  --dimensions country,device,channel \
  --dispatch \
  --output-report rca_oct_2026.md
```

---

## CLI Reference

| Flag | Type | Default | Description |
|:---|:---|:---|:---|
| `--baseline` | `string` | `data/baseline.csv` | Path to baseline-period CSV |
| `--current` | `string` | `data/current.csv` | Path to current-period CSV |
| `--metric` | `string` | `conversions` | Primary metric column to decompose |
| `--secondary-metric` | `string` | `sessions` | Denominator for rate decomposition (set `''` to disable) |
| `--dimensions` | `string` | `country,device,channel` | Comma-separated dimension columns |
| `--dispatch` | `boolean` | `False` | Triggers the Multi-Agent Stakeholder Action Dispatcher |
| `--generate-sample` | `string` | `None` | Synthesizes a mock dataset (`checkout_dropoff`, `payment_gateway_failure`, `mobile_release_regression`, `ad_campaign_fatigue`, or `list`) |
| `--format` | `choice` | `markdown` | Report format: `markdown` or `json` |
| `--output-report` | `string` | `report.md` | Output path for the generated report |

---

## Example Input & Output

### Example Input
The bundled mock dataset (`data/baseline.csv` and `data/current.csv`) contains weekly multi-dimensional conversion snapshots segmented by `country`, `device`, and `channel`:

**`data/baseline.csv`**
```csv
date,country,device,channel,conversions,sessions
2026-10-10,IN,Mobile,Organic,450,9000
2026-10-10,IN,Desktop,Organic,300,5000
2026-10-10,US,Mobile,Paid,600,10000
2026-10-10,US,Desktop,Paid,500,6000
2026-10-10,UK,Mobile,Direct,200,4000
2026-10-10,UK,Desktop,Direct,150,2500
```

**`data/current.csv`**
```csv
date,country,device,channel,conversions,sessions
2026-10-17,IN,Mobile,Organic,460,9100
2026-10-17,IN,Desktop,Organic,290,4900
2026-10-17,US,Mobile,Paid,180,9800
2026-10-17,US,Desktop,Paid,480,5900
2026-10-17,UK,Mobile,Direct,195,3950
2026-10-17,UK,Desktop,Direct,145,2450
```

### Example Output (`python main.py --dispatch`)

```text
=================================================================
STEP 1: Computing Deterministic Cohort Decomposition...
=================================================================
  Target Metric : conversions
  Variance      : 2,200.0 -> 1,750.0 (-20.45%)
  Top Culprit   : US / Mobile / Paid (Delta: -420)
  Worst Rate    : US / Mobile / Paid (6.0% -> 1.8367%, Delta -4.16 pp)

+----------------------------------------------------------------------------------+
|                     METRIC DRIFT WATERFALL SUMMARY (CONVERSIONS)                 |
+----------------------------------------------------------------------------------+
| Baseline Total         |    2,200.0 | ############################               |
+------------------------+------------+--------------------------------------------+
|  [-] US / Mobile / Paid |     -420.0 | vvvvvvvvvvvvvvvvvvvvvv (-93.3%)           |
|  [-] US / Desktop / Paid |      -20.0 | v                      ( -4.4%)          |
|  [-] IN / Desktop / Organic |      -10.0 | v                      ( -2.2%)          |
|  [+] IN / Mobile / Organic |       10.0 | ^                      (  2.2%)          |
+------------------------+------------+--------------------------------------------+
| Current Total (-20.4%) |    1,750.0 | ######################                     |
+----------------------------------------------------------------------------------+

=================================================================
STEP 2: Diagnostic Reasoning & Hypothesis Generation...
=================================================================

### 1. Executive Summary
During the evaluated period, total conversions experienced an overall variance of -450.0 (-20.45%),
shifting from a baseline of 2,200.0 down to 1,750.0. The mathematical decomposition demonstrates
that this degradation was heavily localized rather than systemic, predominantly driven by the
country=US / device=Mobile / channel=Paid cohort. Conversion efficiency collapsed from 6.0% to 1.84%.

### 2. Primary Anomaly Cohort
- Cohort Dimensions: country=US / device=Mobile / channel=Paid
- Absolute Delta: -420.0 conversions
- Contribution to Variance: -93.33% of total downward drift
- Anomaly Classification: Isolated High-Impact Segment Outage

### 3. Plausible Technical & Business Hypotheses
1. Frontend / Checkout Regressions: Recent mobile web checkout deployment introduced a viewport JS error.
2. Third-Party Gateway Failure: Latency spikes or gateway API timeouts on US mobile payment processors.
3. Tracking & Attribution Tag Disruption: Ad pixel tag dropping conversion triggers on Paid traffic.

### 4. Targeted Triage Queries
```sql
-- Query 1: Funnel step-by-step conversion dropoff for culprit cohort
SELECT
    funnel_step,
    COUNT(CASE WHEN event_date = '2026-10-10' THEN user_id END) AS baseline_users,
    COUNT(CASE WHEN event_date = '2026-10-17' THEN user_id END) AS current_users,
    ROUND(COUNT(CASE WHEN event_date = '2026-10-17' THEN user_id END) * 1.0 /
          NULLIF(COUNT(CASE WHEN event_date = '2026-10-10' THEN user_id END), 0) - 1, 4) * 100 AS pct_step_change
FROM analytics_events
WHERE country = 'US' AND device = 'Mobile' AND channel = 'Paid'
GROUP BY 1 ORDER BY 1;
```

=================================================================
STEP 3: Multi-Agent Stakeholder Incident Action Dispatch...
=================================================================

+------------------------------------------------------------------------------------+
|             MULTI-AGENT STAKEHOLDER INCIDENT ACTION DISPATCH MATRIX                |
+------------------------------------------------------------------------------------+
| Severity: SEV-1 (Critical) Culprit: country=US / device=Mobile / channel=Paid      |
| Dispatcher: Deterministic Domain Rules Sub-Agent                                   |
+------------------------------------------------------------------------------------+

  [P0]  Engineering / DevOps Lead (SLA: 2 hours (Critical P0))
         Trigger  : US / Mobile / Paid driving -420 conversions drop (-93.33% of total drift)
         Inspect  : Inspect edge CDN error rates, API gateway latency, and recent deployment commits touching mobile clients for region US.
         Action   : Revert recent client releases or hotfix offending service worker / checkout JS bundles. Verify synthetic health checks for US endpoints.

  [P1]  Growth / Paid Media Lead (SLA: 4 hours)
         Trigger  : Disproportionate drop in Paid acquisition volume and conversion efficiency.
         Inspect  : Audit active ad campaigns on Paid targeting US on Mobile. Verify landing page redirection parameters, UTM tagging, and attribution pixel firing.
         Action   : Pause or reallocate underperforming campaign budgets. Restore missing attribution parameters and verify conversion postback health.

  [P1]  Regional / Geography Manager (SLA: 4 hours)
         Trigger  : Localized KPI deterioration concentrated within region: US.
         Inspect  : Assess regional payment gateway authorization rates (e.g., 3D-Secure, local cards), telecom/ISP routing issues, and local currency checkout services in US.
         Action   : Switch traffic routing to secondary payment processor in US if authorization rate has degraded. Post status page notification if localized banking outage confirmed.

=================================================================
Report exported successfully to: report.md
=================================================================
```

---

## How to Test

### Automated Unit Test Suite
Execute the built-in test suite to verify math decomposition, rate drift, guardrails, dispatch tickets, and synthetic data generation:

```bash
python test_agent.py
# or
python -m unittest test_agent.py -v
```

Expected output:
```text
test_ascii_waterfall_output (__main__.TestKPIAgent) ... ok
test_csv_validation_missing_columns (__main__.TestKPIAgent) ... ok
test_csv_validation_oversized_file (__main__.TestKPIAgent) ... ok
test_dispatch_formatting (__main__.TestKPIAgent) ... ok
test_optional_rate_decomposition_disabled (__main__.TestKPIAgent) ... ok
test_prompt_injection_sanitization (__main__.TestKPIAgent) ... ok
test_rate_decomposition (__main__.TestKPIAgent) ... ok
test_stakeholder_dispatch_offline_mode (__main__.TestKPIAgent) ... ok
test_synthetic_data_scenarios (__main__.TestKPIAgent) ... ok
test_volume_drift_math (__main__.TestKPIAgent) ... ok

----------------------------------------------------------------------
Ran 10 tests in 0.123s

OK
```

### Manual Verification Commands

```bash
# 1. Zero-flag default execution (must exit 0)
python main.py

# 2. Multi-agent stakeholder dispatch (must exit 0)
python main.py --dispatch

# 3. Synthetic sample data generator test
python main.py --generate-sample payment_gateway_failure --dispatch

# 4. JSON output verification
python main.py --format json --output-report sample.json

# 5. Schema validation error guardrail test
python main.py --metric non_existent_column
# Expected: clean exit 1 with available column listing
```

---

## Known Limitations

- **Pre-aggregated CSV Input Required**: The agent expects tabular CSV data with consistent dimension schemas across baseline and current files. It does not execute live transactional database queries directly.
- **Descriptive Dimension Column Naming**: Diagnostic reasoning relies on standard descriptive column headers (e.g., `country`, `device`, `channel`, `campaign`). Obfuscated column names (e.g., `dim_1`, `col_a`) reduce LLM hypothesis specificity.
- **API Rate Limits**: When using Google AI Studio free tiers, per-minute request rate limits apply. The agent cycles across model fallbacks (`gemini-2.5-flash`, `gemini-3.5-flash-lite`, etc.) and falls back to deterministic reasoning if remote quotas are exceeded.
- **Non-deterministic Diagnostic Reasoning**: While mathematical variance decomposition is 100% deterministic and reproducible, LLM-generated qualitative hypotheses and queries will naturally vary across model executions.

---

## Guardrails

The agent implements comprehensive enterprise safety layers:

| Layer | Guardrail | Description |
|:---|:---|:---|
| **Input** | CSV file-size limit | Rejects files > 10 MB before loading into memory |
| **Input** | Row count limit | Rejects CSVs with > 1M rows to prevent memory exhaustion |
| **Input** | Schema verification | Validates required metric and dimension columns before compute |
| **Compute** | Cohort explosion cap | Caps at 10,000 unique dimension combinations; keeps top cohorts by absolute delta |
| **Prompt** | Dimension value sanitization | Strips special characters and truncates long values to prevent prompt injection from CSV data |
| **LLM** | Scope constraint instructions | System-level prompt rules forbid the model from performing arithmetic, executing code, or producing off-topic content |
| **LLM** | Response validation & fallback | Validates LLM responses and cycles through model candidates (`gemini-2.5-flash`, `gemini-3.5-flash-lite`, etc.) |
| **Output** | Sensitive path guard | Refuses to write reports to protected system directories (`/etc`, `/usr`, `C:\Windows`, etc.) |
| **Offline** | Graceful Deterministic Fallback | Operates reliably without network or API key, providing zero-flag reproducibility |

---

## Security & Privacy Considerations

- **Secrets Handling**: The API key is loaded via environment variable or `.env` file (managed by `python-dotenv`). The `.gitignore` excludes `.env` to prevent accidental commits. The `.env.example` contains only placeholder values.
- **Data Privacy**: Only aggregated cohort-level statistics (not raw row-level data) are sent to the Gemini API. Dimension values are sanitized before prompt assembly.
- **Safety**: The agent does not execute shell commands, write to production databases, or perform destructive operations.

---

## Future Improvements

- [ ] Add direct BigQuery / Snowflake data warehouse connectors for real-time drift extraction.
- [ ] Support local models via Ollama for air-gapped enterprise deployments.
- [ ] Add streaming responses for interactive terminal inspection.
- [ ] Multi-period trend analysis (3+ snapshots) for drift velocity and seasonality adjustment.
- [ ] PagerDuty / Slack Webhook integration for direct automated ticket publishing.

---

## License

*This project is contributed under the repository's open-source license.*
