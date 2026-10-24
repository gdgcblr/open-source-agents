# TracePilot

> An evidence-driven AI troubleshooting agent that transforms raw test failures and stack traces into reproducible bug reports with verifiable line-level evidence.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: When a test fails or a Python/Linux application crashes, developers waste valuable time parsing noisy logs, hunting down stack frames manually, and piecing together reproduction steps. Existing AI chat assistants offer general explanations, but often hallucinate root causes without grounding them in the actual log lines.
- **Intended Users**: Software developers, QA engineers, and DevOps/SRE teams looking for automated, evidence-backed test failure diagnosis and bug reporting.

### Key Features
- **Evidence-Linked Diagnosis**: Every identified root cause and hypothesis points directly to confirmed fact lines and stack frame line numbers in the raw log.
- **Tool-Using Agent Architecture**: Incorporates specialized deterministic tools (`LogAnalyzerTool` and `TestInspectorTool`) to parse Python tracebacks and test summaries instead of relying solely on ungrounded text generation.
- **Structured Reproduction Report**: Generates a comprehensive Markdown bug report detailing confirmed facts, hypotheses, environment details, expected vs. actual behavior, and step-by-step reproduction instructions.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework**: Custom tool-using agent runner with Google GenAI SDK integration (`google-genai`)
- **Core Libraries**: Pydantic 2.0+, Pytest (for testing), Dotenv
- **Models**: Gemini 2.5 Flash / compatible LLM runtimes

---

## Architecture & Data Flow

```
[Raw Error Log / Test Output] --> [TracePilot Agent Runner]
                                          |
        +---------------------------------+---------------------------------+
        |                                                                   |
        v                                                                   v
[LogAnalyzerTool] (Extracts errors,        [TestInspectorTool] (Parses test status,
 stack frames & evidence line numbers)       failing tests & assertion failures)
        |                                                                   |
        +---------------------------------+---------------------------------+
                                          |
                                          v
                      [Evidence-Linked Diagnosis & Hypotheses]
                                          |
                                          v
                      [Structured Markdown Reproduction Report]
```

---

## Prerequisites

- Python 3.10 or higher
- `pip` package manager
- (Optional) Google Gemini API key (`GEMINI_API_KEY`) for advanced LLM reasoning (falls back to deterministic expert analysis when offline).

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/trace-pilot
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables:**
   ```bash
   cp .env.example .env
   # Edit .env and add your GEMINI_API_KEY if desired
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | No | *None* | API key for Google Gemini LLM integration |
| `MODEL_NAME` | No | `gemini-2.5-flash` | LLM model identifier |
| `LOG_LEVEL` | No | `info` | Logging verbosity (`debug`, `info`, `warn`, `error`) |

---

## How to Run

Run TracePilot on the included sample error log:
```bash
python main.py --file sample_error.log --output bug_report.md
```

Or pass any custom log file or pipe content from stdin:
```bash
pytest --tb=short > test_failures.log
python main.py --file test_failures.log --output report.md
```

---

## Example Input & Output

### Example Input (`sample_error.log`)
```
FAILED tests/test_database.py::test_connection_pool - ConnectionPoolExhaustedError: Connection pool exhausted: active=5, max=5
File "db/pool.py", line 88, in acquire
    raise ConnectionPoolExhaustedError("Connection pool exhausted: active=5, max=5")
```

### Example Output (`bug_report.md` snippet)
```markdown
# 🛡️ TracePilot Investigation Report

## 📋 Executive Summary
- **Total Tests Failed**: 1
- **Total Errors Logged**: 1
- **Evidence Line Numbers**: `16, 21, 28`

## 🔍 Confirmed Facts (Evidence-Linked)
- ✅ Test 'tests/test_database.py::test_connection_pool' failed at output line 16.
- ✅ Error encountered at line 28: ConnectionPoolExhaustedError: Connection pool exhausted: active=5, max=5
- ✅ Stack frame in db/pool.py at line 88 (acquire).

## 🧠 Hypotheses & Root Cause Analysis
- **Hypothesis**: Database connection pool capacity is exceeded because active connections are not being properly released or timeout threshold is too short under load.
  - **Confidence**: `High`
  - **Supporting Evidence**: ConnectionPoolExhaustedError triggered when active=5, max=5.
```

---

## How to Test

Run the automated test suite using pytest:
```bash
pytest
```

---

## Known Limitations

- Currently parses standard Python traceback formats and pytest outputs; custom log formats may require custom regex patterns in `LogAnalyzerTool`.
- LLM synthesis requires an active internet connection and valid API key when online mode is explicitly enabled.

---

## Security & Privacy Considerations

- **Secrets Handling**: API keys are loaded exclusively through environment variables and `.env` (ignored by `.gitignore`).
- **Data Privacy**: Log snippets are processed locally by deterministic regex parsers. When cloud LLM features are used, only relevant traceback fragments are sent.
- **Safety**: TracePilot is a read-only diagnostic and reporting tool; it does not execute arbitrary shell commands or modify system state.

---

## Future Improvements

- [ ] Add support for Node.js (Jest/Mocha) and Go test output parsers.
- [ ] Integrate interactive debugging prompts based on stack frame inspection.
- [ ] Add webhook output for GitHub Issue creation.

---

## License

*This project is contributed under the repository's open-source license.*
