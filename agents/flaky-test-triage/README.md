# Flaky Test Triage Agent

> Paste a failing test log and get a verdict (flaky, real bug, environment issue or test issue) with evidence and a fix.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: QA teams lose hours re-running red builds to decide if a failure is a real bug or just noise.
- **Intended Users**: QA automation engineers, SDETs and developers who own CI pipelines.

### Key Features
- **Log parsing**: finds framework, test name, error type and stack excerpt (Selenium, REST Assured, pytest, Jenkins).
- **Rule-based classification**: timing, environment, test data, locator change, or assertion failure.
- **Run history check**: pass rate and pass/fail flips over the last runs.
- **Final verdict**: combines log and history signals, then writes a short Markdown report.

---

## Technical Stack
- **Language & Runtime**: Python 3.10+
- **Agent Framework**: Google ADK (SequentialAgent with two LlmAgents)
- **Model**: Gemini 3.6 Flash (configurable)
- **Tools**: plain Python, standard library only, fully unit tested

---

## Architecture & Data Flow

```
[Failing log] --> [Analyzer agent] --tools--> parse_test_log
                        |                     classify_failure
                        |                     check_flakiness_history
                        |                     combine_signals
                        v   (state: analysis)
                  [Reporter agent] --> [Markdown triage report]
```

The tools do the facts. The model only orders the tool calls and writes the report, so results are repeatable and easy to test.

---

## Prerequisites
- Python 3.10+ and pip
- A free Gemini API key from https://aistudio.google.com/apikey

---

## Installation & Setup

```bash
cd agents/flaky-test-triage
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # then put your GOOGLE_API_KEY in .env
```

## Configuration & Environment Variables

| Variable | Purpose | Example |
| :--- | :--- | :--- |
| `GOOGLE_API_KEY` | Gemini API key | `your_gemini_api_key_here` |
| `GOOGLE_GENAI_USE_VERTEXAI` | Use AI Studio, not Vertex | `FALSE` |
| `MODEL_NAME` | Gemini model | `gemini-3.6-flash` |

---

## How to Run

```bash
# Web UI (run from agents/flaky-test-triage)
adk web
# pick "flaky_test_triage", then paste a log from sample_logs/

# Or terminal
adk run flaky_test_triage
```

---

## Example Input & Output

### Example Input
Contents of `sample_logs/01_selenium_timeout.log` (a `TimeoutException` waiting for a payment spinner).

### Example Output
```
## Verdict: flaky (confidence 98%)
Test: CheckoutTest.testPaymentSpinnerDisappears | Framework: selenium
### Why
- TimeoutException while waiting for an element to disappear
- Last 10 runs: 5 passes, 5 fails, 8 flips between pass and fail
### Recommended fix
- Use an explicit wait on the exact condition instead of a fixed delay
- Re-find elements after page updates
### Next action
- Fix the test wait, do not raise a product bug
```
(Exact wording varies by model run.)

Sample logs and expected verdicts:

| Log | Expected verdict |
| :--- | :--- |
| `01_selenium_timeout.log` | flaky |
| `02_api_assertion.log` | real_bug |
| `03_env_connection.log` | environment_issue |
| `04_locator_changed.log` | test_issue |
| `05_pytest_data_conflict.log` | test_issue |

---

## How to Test

```bash
pytest -q        # 57 tests (tools, guardrails, batch, fixer), no API key needed
```

---

## Batch Triage Studio (second agent)

Run `adk web` and pick **batch_triage_studio** for team-level triage. It makes no LLM call per log, so a folder of 200 logs is instant and uses almost no API quota.

| Feature | What it does |
| :--- | :--- |
| Batch triage | Triages every `.log` or `.txt` in a folder (default `sample_batch/`) |
| Failure clustering | Groups failures by root cause and shared factor, e.g. "4 of 12 failed on `node=selenium-grid-chrome-3`" |
| Dashboard | Writes `reports/triage_dashboard.html` (donut chart, cluster bars, failure table, copy box) |
| Slack / Teams report | Writes `reports/slack_report.txt` and `reports/teams_report.md` |
| Auto-fix diff | `suggest_fix_diff` returns a patch. It never edits your files |

Auto-fix rules:
- `Thread.sleep(...)` followed by `findElement` becomes an explicit `WebDriverWait` (imports added)
- Positional XPath such as `//div[3]/button[2]` becomes a `data-testid` selector marked FIXME
- Hard-coded test emails become unique per run (`uuid`)

Try these prompts in the studio:
1. `Triage sample_batch`
2. `Suggest a fix for sample_src/CheckoutTest.java`
3. `Suggest a fix for sample_src/ProfileTest.java` and `sample_src/test_orders.py`

No API key needed for the core engine:

```bash
python -m flaky_test_triage.batch sample_batch
```

Extra safety for these features:
- Folders and source files must be inside the project. `..`, absolute paths outside it and hidden files (like `.env`) are rejected.
- Each log goes through the same injection check and secret redaction before analysis. Bad files are skipped and counted.
- Dashboard text is HTML escaped, so a malicious log cannot inject script into the page.
- Only `.log`, `.txt` (logs) and `.java`, `.py`, `.kt`, `.js`, `.ts` (source) files are read, with size limits.

---

## Guardrails & Security

Defense in depth, implemented in `flaky_test_triage/guardrails.py`:

| Layer | What it does |
| :--- | :--- |
| Input check | Blocks empty input, non-log text, and prompt-injection phrases hidden in a log |
| Secret redaction | Masks API keys, bearer tokens, JWTs, AWS keys, passwords and emails BEFORE the log reaches Gemini |
| Size limit | Logs over 30,000 characters keep head and tail, middle is cut |
| Tool argument checks | Validates type, size and path characters of every tool call |
| Prompt hardening | Both agents treat the log as data and never follow instructions inside it |
| Output check | Re-redacts secrets in the report and enforces the report format |
| Safe blocking | A blocked request skips the model entirely and returns a clear message |
| Retries | Backoff on 429/500/503/504 so temporary Gemini errors do not crash a run |

Other security notes:
- Tools are read-only and deterministic. The agent cannot run commands, write files or call other services.
- `.env`, `.adk/` and `*.db` are gitignored. ADK stores sessions in `.adk/`, which can contain pasted logs.
- Redaction is pattern based, so still review logs for company secrets before sharing outside your team.
- If a key is ever pasted into a chat or committed, rotate it immediately.

---

## Known Limitations
- Classification is keyword based, so unusual error messages return `unclear`.
- History comes from the sample file `flaky_test_triage/test_history.json`, not a live CI system.
- Only one log is analysed per request.

## Security & Privacy Considerations
- No secrets are committed. Keep your key in `.env` only.
- Logs are sent to the Gemini API, so redact tokens, emails and internal hostnames first.

## Future Improvements
- Pull history from Jenkins or GitHub Actions APIs.
- Auto-rerun a failing test N times to measure flakiness live.
- Open a Jira ticket for confirmed real bugs.

## License
MIT, see the repository root [LICENSE](../../LICENSE).
