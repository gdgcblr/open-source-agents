# Incident Analyzer

> AI-powered agent that indexes your Python codebase via AST, then correlates runtime errors, logs, and stack traces against the code structure to diagnose root causes and suggest validated code fixes.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: When a Python application crashes or produces unexpected output, developers spend significant time manually tracing through stack traces, matching error lines to source code, understanding call chains, and formulating fixes. This is especially painful in unfamiliar codebases or during on-call incident response.
- **Intended Users**: Software developers, SREs, on-call engineers, and teams performing post-incident reviews on Python codebases.

### Key Features
- **One-Time AST Indexing**: Parses your entire Python codebase using the `ast` module to build a structured specification (function signatures, call graphs, class hierarchies, docstrings, source snippets) — stored as a portable JSON file.
- **Stack Trace Correlation**: Automatically extracts traceback frames from logs and maps them to the indexed codebase symbols, identifying exactly which functions and call chains are involved.
- **Actual vs Expected Comparison**: Optionally accepts actual and expected output to provide richer diagnosis context.
- **Structured LLM Diagnosis**: Uses Google Gemini to produce structured JSON diagnoses with root cause, severity, affected symbols, concrete before/after code fixes, and prevention tips.
- **AST Syntax Validation**: Every suggested code fix is validated through `ast.parse()` before being presented, ensuring syntactic correctness.
- **Log Sanitization (Security Guardrail)**: Automatically strips API keys, tokens, passwords, database URIs, email addresses, IP addresses, JWT tokens, private keys, and home directory paths from logs **before** they are sent to any external LLM API.
- **Offline Mock Mode**: Full functionality without API keys using intelligent heuristic-based mock diagnosis — enabling testing, CI, and demos without external dependencies.

---

## Technical Stack

- **Language & Runtime**: Python 3.9+
- **Agent Framework / Core Library**: Vanilla Python with `ast` module for static analysis
- **Models**: Google Gemma (open-weights) / Gemini 2.5 Flash (via `google-genai` SDK) / Mock provider for offline use
- **Key Libraries**: Pydantic v2 (structured schemas), argparse (CLI), pytest (testing)

---

## Architecture & Data Flow

```
                        ┌─────────────────────────────┐
                        │   ONE-TIME SETUP (index)     │
                        │                              │
 [Python Codebase] ───► │  AST Parser (ast module)     │
                        │  ├─ Functions & signatures   │
                        │  ├─ Classes & methods        │
                        │  ├─ Call graphs              │
                        │  ├─ Imports & decorators     │
                        │  └─ Source snippets           │
                        │                              │
                        │  ───► .incident-spec.json    │
                        └─────────────────────────────┘

                        ┌─────────────────────────────┐
                        │   INCIDENT ANALYSIS          │
                        │                              │
 [Error Logs /     ───► │  1. Log Sanitizer            │ ◄── Security Guardrail
  Stack Traces]         │     (strip secrets, PII)     │
                        │                              │
 [Actual Output]  ───► │  2. Traceback Frame Extractor │
 [Expected Output] ──► │     (regex-based parsing)     │
                        │                              │
                        │  3. Symbol Correlator         │
                        │     (match frames ↔ AST spec)│
                        │                              │
                        │  4. LLM Diagnosis Engine      │
                        │     (Gemini / Mock mode)     │
                        │                              │
                        │  5. Fix Syntax Validator      │ ◄── Safety Guardrail
                        │     (ast.parse validation)   │
                        │                              │
                        └──────────┬──────────────────┘
                                   │
                                   ▼
                        ┌─────────────────────────────┐
                        │  STRUCTURED DIAGNOSIS        │
                        │  ├─ Root cause analysis      │
                        │  ├─ Severity assessment      │
                        │  ├─ Affected symbols & files │
                        │  ├─ Before/after code fixes  │
                        │  └─ Prevention tips           │
                        └─────────────────────────────┘
```

---

## Prerequisites

Before running this project, ensure you have:
- **Python 3.9+**
- **pip** package manager
- **Google Gemini / Gemma API key** (only for live API mode; not required for `--mock` mode or automated tests)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/incident-analyzer
   ```

2. **Set up the virtual environment and install dependencies:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Linux/macOS
   # .venv\Scripts\activate    # Windows

   pip install -r requirements.txt
   ```

3. **Configure environment variables (optional — only for live Gemini mode):**
   ```bash
   cp .env.example .env
   # Edit .env and set your GEMINI_API_KEY
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Only for live mode | *None* | Google Gemini API key. Not needed with `--mock`. |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Gemini model identifier |
| `LOG_LEVEL` | No | `info` | Logging verbosity (`debug`, `info`, `warning`, `error`) |

---

## How to Run

### Step 1: Index Your Codebase (One-Time Setup)

```bash
# Index a Python project (generates .incident-spec.json)
python main.py index /path/to/your/python/project

# Also generate a human-readable Markdown spec (spec.md)
python main.py index /path/to/project --markdown

# With custom output path
python main.py index /path/to/project -o my-spec.json

# Exclude specific directories
python main.py index /path/to/project --exclude "tests,migrations,scripts"
```

This generates a `.incident-spec.json` file (and optional `spec.md`) containing the full AST specification.

### 30-Second Bundled Walkthrough

You can test the agent right away using the bundled sample buggy service without any configuration:

```bash
# 1. Index the sample service and generate Markdown spec
python main.py index examples/buggy_service --markdown

# 2. Run Incident Diagnosis in Mock Mode (zero API keys needed)
python main.py analyze \
    --spec examples/buggy_service/.incident-spec.json \
    --log-file examples/buggy_service/incident.log \
    --expected '{"status": "confirmed", "final_amount": 45.0}' \
    --actual 'AttributeError: NoneType object has no attribute get' \
    --mock
```

### Step 2: Analyze an Incident

```bash
# From a log file (mock mode — no API key needed)
python main.py analyze --spec /path/to/project/.incident-spec.json \
    --log-file error.log --mock

# Inline log text
python main.py analyze --spec .incident-spec.json \
    --log "TypeError: expected str, got NoneType" --mock

# With actual vs expected output
python main.py analyze --spec .incident-spec.json \
    --log-file error.log \
    --actual "None" \
    --expected '["processed", "data"]' \
    --mock

# Pipe from another command
pytest 2>&1 | python main.py analyze --spec .incident-spec.json --mock

# Live mode with Gemini (requires GEMINI_API_KEY)
python main.py analyze --spec .incident-spec.json --log-file error.log

# JSON output
python main.py analyze --spec .incident-spec.json --log-file error.log --mock --json

# Save report to file
python main.py analyze --spec .incident-spec.json --log-file error.log --mock \
    --save diagnosis-report.json
```

---

## Example Input & Output

### Example Input (`incident.log` with sensitive token)
```
2026-10-24 12:00:01 [DEBUG] Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c3JfNDkyMCJ9.abcdef1234567890
2026-10-24 12:00:02 [ERROR] Unhandled exception occurred during order checkout
Traceback (most recent call last):
  File "examples/buggy_service/service.py", line 44, in <module>
    process_order(sample_order)
  File "examples/buggy_service/service.py", line 32, in process_order
    final_amount = apply_discount_code(subtotal, discount)
  File "examples/buggy_service/service.py", line 22, in apply_discount_code
    rate = discount.get("rate", 0.0)
AttributeError: 'NoneType' object has no attribute 'get'
```

### Example Output (Mock Mode)
```
======================================================================
  INCIDENT ANALYSIS REPORT
======================================================================

Severity:   🟡 MEDIUM
Confidence: 50%

──────────────────────────────────────────────────────────────────────
ROOT CAUSE
──────────────────────────────────────────────────────────────────────
[MOCK MODE] Accessing attribute on None or incorrect object type

──────────────────────────────────────────────────────────────────────
AFFECTED SYMBOLS
──────────────────────────────────────────────────────────────────────
  • process_order @ service.py:27-38
    Relevance: Traceback frame at line 32 in function 'process_order'
  • apply_discount_code @ service.py:16-24
    Relevance: Traceback frame at line 22 in function 'apply_discount_code'

──────────────────────────────────────────────────────────────────────
SUGGESTED FIXES & PATCHES
──────────────────────────────────────────────────────────────────────
  Fix #1: service.py [Patch Verified ✅]
  Explanation: Review process_order at line 27 - Traceback frame at line 32
  Unified Diff:
    --- a/service.py
    +++ b/service.py
    @@ -1,3 +1,4 @@
     # Code at service.py:27
     def process_order():
    +    # Safe guard added
         pass

  Fix #2: service.py [Patch Verified ✅]
  Explanation: Review apply_discount_code at line 16 - Traceback frame at line 22
  Unified Diff:
    --- a/service.py
    +++ b/service.py
    @@ -1,3 +1,4 @@
     # Code at service.py:16
     def apply_discount_code():
    +    # Safe guard added
         pass

──────────────────────────────────────────────────────────────────────
PREVENTION TIPS
──────────────────────────────────────────────────────────────────────
  💡 [Mock] Add input validation and type checking
  💡 [Mock] Add comprehensive error handling with specific exceptions
  💡 [Mock] Write unit tests covering edge cases

======================================================================
```

---

## How to Test

Run the full test suite (no API key required — all tests use mock mode or pure logic):

```bash
# Run all tests
pytest tests/ -v

# Run specific test modules
pytest tests/test_indexer.py -v      # AST indexer tests
pytest tests/test_sanitizer.py -v   # Log sanitizer tests
pytest tests/test_diagnoser.py -v   # Diagnosis engine tests

# Run with coverage
pytest tests/ -v --tb=short
```

All tests are fully self-contained:
- AST indexer tests create temporary Python files and verify parsing accuracy.
- Sanitizer tests verify that 15+ categories of sensitive data are correctly redacted.
- Diagnoser tests validate the full pipeline including frame extraction, symbol correlation, LLM response parsing, and mock diagnosis.

---

## Known Limitations

- **Python-only AST indexing**: Currently indexes Python files only. TypeScript, Go, and other languages are not supported.
- **Stack trace format**: Traceback extraction supports standard CPython traceback format. Non-standard log formats (e.g., custom structured logging frameworks) may not be fully parsed.
- **Mock mode heuristics**: Mock mode uses simple keyword-based error type detection and does not perform deep semantic analysis.
- **LLM fix accuracy**: Suggested code fixes from Gemini are validated for syntax but not for semantic correctness. Always review fixes before applying.
- **Large codebases**: Very large codebases (10,000+ files) may produce large spec files. Consider using `--exclude` to limit indexing scope.
- **Tested on**: macOS and Linux. Windows support is expected but not fully verified.

---

## Security & Privacy Considerations

- **Secrets Handling**: The log sanitizer automatically scrubs 15+ categories of sensitive data (API keys, bearer tokens, AWS credentials, passwords, database URIs, emails, IPs, JWTs, private keys, home directory paths) **before** any data is sent to an external LLM. Credentials are loaded exclusively via environment variables.
- **Data Privacy**: Log text and codebase AST specifications are sent to the Google Gemini API when running in live mode. Use `--mock` mode to prevent any external data transmission. The sanitizer ensures that even in live mode, sensitive tokens and PII are redacted.
- **Safety**: This agent performs **read-only static analysis** using Python's `ast` module. It never executes, imports, or evaluates target code. Suggested fixes are output as text and never auto-applied without explicit user action.

---

## Future Improvements

- [ ] Support multi-language AST indexing (TypeScript via tree-sitter, Go via `go/ast`).
- [ ] Add structured log format support (JSON logs, logfmt).
- [ ] Support local models via Ollama for fully offline operation.
- [ ] Add `--apply` flag to auto-apply validated patches as unified diffs.
- [ ] Interactive mode for conversational follow-up diagnosis.
- [ ] Integration as a GitHub Action for automated PR incident analysis.

---

## License

*This project is contributed under the repository's open-source license.*
