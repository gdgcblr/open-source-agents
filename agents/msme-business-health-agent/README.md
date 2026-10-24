# MSME Business Health Agent

> An agent that reads a small business's multi-tab spreadsheet (one tab per department) and gives the owner a plain-language, percentage-based health overview, then finds where orders and tasks sit idle in the process.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Small and medium business (MSME) owners keep their data in spreadsheets, with one tab per department (sales, inventory, support, orders). They rarely have time or analytics skills to see the whole business at once: how clean the data is, which department is unhealthy, and where work gets stuck. Delays, such as orders waiting days between packing and dispatch, quietly cost money and customers.
- **Intended Users**: MSME owners and managers who run their business from Google Sheets or Excel and want a daily or weekly health check without hiring an analyst.

### Key Features
- **360-degree overview on first upload**: per tab, the number of rows and columns, date range, % missing cells, % duplicate rows, % invalid dates, a guessed department, and a Good / Watch / Critical health score, plus an overall workbook score.
- **Messy-sheet cleaning**: detects header rows under title lines, removes blank rows and totals rows, and parses dates day-first (DD/MM/YYYY).
- **Process X-ray (bottleneck mining)**: finds any tab that looks like an event log (case ID + activity + timestamp), traces each case, computes idle hours between steps and ranks the biggest bottlenecks, with the % of cases affected.
- **Computed, not guessed**: every number comes from pandas code, not from an LLM.
- **Planned**: department KPIs, PII masking, an LLM-written owner report with draft customer messages, and weekly comparison (see Future Improvements).

> **Status: work in progress.** The overview profiler and the process miner are implemented and tested. The LLM narrator is not implemented yet.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+
- **Agent Framework / Core Library**: Vanilla Python pipeline (pandas, pydantic). No agent framework is used yet. The code is organised as small modules, so it can be wrapped in an agent framework later.
- **Models**: None used by the current features. A hosted LLM (Anthropic Claude) is planned for the narration step only.
- **External APIs / Tools**: Google Sheets and Drive APIs via `gspread` (read-only, optional), `openpyxl` for local `.xlsx` files, `python-dotenv`, `pytest`.

---

## Architecture & Data Flow

```
[Google Sheet / .xlsx]
        |
        v
  [ingest.py]  -> one raw DataFrame per tab
        |
        v
  [clean.py]   -> header row detected, blank and totals rows removed
        |
        +--> [classifier.py]    tab -> department guess + confidence
        |
        +--> [profiler.py]      rows, % missing, % duplicates, % invalid dates, health score
        |
        +--> [process_miner.py] event log? -> idle time per step, ranked bottlenecks
        |
        v
  [JSON overview report]  --(planned)--> [PII masking] --> [LLM narrator] --> [owner report]
```

Execution flow: the command-line entry point (`src/main.py`) loads the workbook, cleans each tab, and builds the overview from the profiler. The process miner is implemented as a separate module and covered by tests, and will be wired into the CLI output in the next step. Design rule: **code computes every number; the LLM (once added) only explains them.**

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.11 or higher
- pip
- Optional, for live Google Sheets: a Google Cloud service account with the Sheets and Drive APIs enabled, with the target sheet shared (Viewer) with the service account's email
- Optional, for the planned narrator step: an Anthropic API key (paid third-party API)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/msme-business-health-agent
   ```

2. **Set up the virtual environment / install dependencies:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Copy the example environment file and fill in your own values:
   ```bash
   # Linux/macOS:
   cp .env.example .env
   # Windows (Command Prompt):
   copy .env.example .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `ANTHROPIC_API_KEY` | No (not used yet) | *None* | Anthropic API key for the planned narrator step |
| `GOOGLE_CREDENTIALS_PATH` | Only for Google Sheets | `credentials.json` | Path to your service account JSON key |
| `SHEET_ID` | Only for Google Sheets | *None* | The ID from your Google Sheet URL |

Local `.xlsx` files need no variables at all. Never commit `.env` or `credentials.json`; both are gitignored.

---

## How to Run

Generate the synthetic sample workbook, then run the overview on it:

```bash
python scripts/make_sample_workbook.py
python -m src.main overview --file data/sample_workbook.xlsx --out data/overview.json
```

Using a live Google Sheet instead:

```bash
python -m src.main overview --sheet-id YOUR_SHEET_ID
```

---

## Example Input & Output

### Example Input
A synthetic 4-tab workbook (`Sales`, `Inventory`, `Support Tickets`, `Order Events`) generated by `scripts/make_sample_workbook.py`. The `Sales` tab is deliberately messy: title rows above the header, mixed date formats, blank amounts, 3 duplicate rows, an impossible date (`31/02/2026`) and a totals row.

```bash
python -m src.main overview --file data/sample_workbook.xlsx
```

### Example Output
Genuine run, workbook summary:

```json
{
  "sheets": 4,
  "total_rows": 246,
  "overall_health_score": 96.3,
  "overall_health": "Good"
}
```

Per-sheet results:

| Sheet | Department (guessed) | Rows | Missing | Duplicate rows | Invalid dates | Health score |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Sales | Sales | 63 | 1.9% | 3 (4.8%) | 1.6% | 89.3 (Good) |
| Inventory | Inventory | 8 | 0.0% | 0 | 0.0% | 100.0 (Good) |
| Support Tickets | Support | 25 | 4.0% | 0 | 0.0% | 96.0 (Good) |
| Order Events | Operations | 150 | 0.0% | 0 | 0.0% | 100.0 (Good) |

Process miner result on the `Order Events` tab (30 orders, 150 events). The bottleneck is deliberately planted in the synthetic data:

```json
{
  "transition": "Packed -> Dispatched",
  "cases": 30,
  "avg_hours": 45.8,
  "p90_hours": 62.2,
  "cases_over_threshold": 28,
  "pct_cases_over_threshold": 93.3
}
```

That is 28 of 30 orders (93.3%) idle for more than 24 hours between packing and dispatch.

---

## How to Test

```bash
python scripts/make_sample_workbook.py
python -m pytest -q
```

Expected result: `5 passed`. The tests use only the synthetic workbook, need no API keys and make no network calls.

---

## Known Limitations

- **Date ambiguity**: dates are parsed day-first (DD/MM/YYYY). Data in MM/DD/YYYY format will be misread.
- **Heuristic cleaning**: header detection looks at the first 10 rows; merged cells, several tables on one tab, or deeper headers may be cleaned wrongly.
- **Keyword-based classification**: unusual tab names may return `Unknown` or low confidence and need owner confirmation.
- **Simple health score**: a fixed-weight heuristic (missing %, duplicate %, invalid-date %), not a calibrated business metric.
- **Process mining needs an event log**: a tab with a case ID, an activity and a timestamp. Without one, bottleneck analysis is skipped.
- **Not yet in the CLI output**: the process miner is tested but not yet printed by `src.main`.
- **Google Sheets loading is untested** against a live sheet at the time of writing; local `.xlsx` is the tested path.
- **Not yet implemented**: department KPIs, cross-tab linking, PII masking, LLM narration, weekly comparison.
- **Platforms**: developed and tested on Linux. Windows: core overview tests verified; full suite verification in progress. macOS: untested.

---

## Security & Privacy Considerations

- **Secrets Handling**: credentials are read from a local `.env` file and a service account JSON key, both gitignored. Only placeholder values are in `.env.example`.
- **Data Privacy**: the current features run entirely locally and send no data to any third party, apart from reading your own Google Sheet if you use that option. The planned narrator step will send only aggregated, PII-masked numbers to the LLM, never raw customer rows.
- **Safety**: Google Sheets access uses read-only scopes. The agent does not execute shell commands or arbitrary code. Customer messages, when added, will be drafts for the owner to approve and will never be sent automatically.

---

## Future Improvements

- [x] Ingest, cleaning, department classification and data-quality overview
- [x] Process miner (idle time between steps, ranked bottlenecks, process variants)
- [ ] Print the bottleneck block in the CLI report
- [ ] Department KPIs and cross-tab links (e.g. orders without invoices)
- [ ] PII masking before any LLM call
- [ ] LLM narrator with schema-validated JSON output and a Markdown owner report
- [ ] Weekly mode with week-over-week comparison (SQLite)
- [ ] Test the Google Sheets loader against a live sheet

---

## License

*This project is contributed under the repository's open-source license.*
