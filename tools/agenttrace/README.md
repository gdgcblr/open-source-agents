# AgentTrace

> Offline deterministic diagnostics and failure pattern analysis for AI agent execution traces.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Autonomous and semi-autonomous AI agents can fail in subtle, multi-step ways: getting stuck in repetitive tool call loops, encountering silent timeouts, or dropping tool results without clear error reporting. Debugging these traces manually from raw logs is slow and error-prone.
- **Intended Users**: AI agent developers, prompt engineers, and evaluators who need an instant, offline, privacy-safe tool to inspect execution traces and pinpoint common failure modes.

### Key Features
- **Deterministic Rule Engine**: Evaluates execution traces using rule-based heuristics to detect explicit errors, repeated identical tool calls (loops $\ge$ 3), timeout indicators, and missing tool outputs in completed traces.
- **Privacy-First & Offline**: Operates completely locally without LLM calls, external APIs, cloud connections, or network dependencies.
- **Interactive Web Dashboard**: Streamlit interface supporting `.json` file upload, direct JSON paste/edit, metrics summary, categorized findings expanders, and chronological event timeline.
- **Diagnostic Export**: Download structured JSON diagnostic reports containing severity levels, cited evidence, and actionable recommendations.
- **Synthetic Demo Traces**: Pre-loaded synthetic examples demonstrating both clean executions and multi-pattern failure investigations.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Core Engine**: Pure Python standard library (`json`, `typing`, `pathlib`)
- **Web Dashboard**: Streamlit ($\ge$ 1.30.0)
- **Automated Testing**: pytest ($\ge$ 7.4.0)
- **Model Providers**: None (100% deterministic, offline rule-based heuristics)
- **External APIs / Tools**: None (zero cloud, network, or third-party API dependencies)

---

## Architecture & Data Flow

```
[User Input: File Upload or Paste]
               │
               ▼
   [Validation & Normalization]
   - Validates root object & events array
   - Normalizes tool input via canonical JSON sorting
               │
               ▼
    [Deterministic Analyzer] (analyzer.py)
   - Evaluates explicit error events (Critical / High)
   - Detects repeated tool calls >= 3 (High)
   - Scans for timeout indicators (Medium)
   - Checks unmatched tool calls when complete: true (Medium)
   - Validates event and call IDs (Medium)
               │
               ▼
     [Structured Report Output]
   - Streamlit Dashboard (app.py): Metrics, Findings, Timeline
   - Downloadable JSON Diagnostic Report
```

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.10 or higher
- `pip` (Python package installer)
- No API keys, credentials, or cloud accounts are needed.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/agenttrace
   ```

2. **Set up virtual environment & install dependencies:**
   - **On Windows (PowerShell):**
     ```powershell
     python -m venv .venv
     .venv\Scripts\Activate.ps1
     pip install -r requirements.txt
     ```
   - **On Linux / macOS:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     pip install -r requirements.txt
     ```

3. **Configure Environment Variables:**
   No environment variables or API keys are required for v1. You can inspect `.env.example` for confirmation:
   ```bash
   # Optional: inspect .env.example
   cat .env.example
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| *None* | No | N/A | AgentTrace v1 runs entirely offline and requires no environment variables. |

---

## How to Run

Launch the Streamlit web dashboard:

```bash
# Ensure virtual environment is activated
streamlit run app.py
```

Once started, open your web browser at the URL provided by Streamlit (typically `http://localhost:8501`).

---

## AgentTrace Event Schema & Examples

Traces must conform to the documented AgentTrace JSON schema.

### Root Object Specification
| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `events` | array of objects | **Yes** | Chronological list of trace events. |
| `name` | string | No | Descriptive name for the trace run. |
| `complete` | boolean | No | Whether the agent declared execution complete. Missing result checks run only when `complete: true`. |

### Event Object Specification
Each event in `events` may contain:
- `id` (string / number): Unique event identifier.
- `type` (string): Event type (e.g., `tool_call`, `tool_result`, `tool_output`, `error`).
- `tool` (string): Tool name for tool calls.
- `input` (any): Input parameters for the tool call (normalized deterministically).
- `output` (string / any): Tool execution output.
- `error` (string / any): Error message or stack trace.
- `call_id` (string / number): ID of the corresponding `tool_call` referenced by a `tool_result`.
- *Unknown fields*: Preserved as-is in the timeline view.

### Example Input (`clean_trace.json` — Synthetic)
```json
{
  "name": "Synthetic Clean Agent Trace Demo",
  "complete": true,
  "events": [
    {
      "id": "call-1",
      "type": "tool_call",
      "tool": "search_documentation",
      "input": {"query": "AgentTrace architecture overview"}
    },
    {
      "id": "res-1",
      "type": "tool_result",
      "call_id": "call-1",
      "output": "Found 3 matching sections in docs/architecture.md."
    }
  ]
}
```

### Example Diagnostic Output (Report JSON)
```json
{
  "trace_name": "Synthetic Clean Agent Trace Demo",
  "event_count": 2,
  "finding_count": 1,
  "findings": [
    {
      "severity": "Info",
      "title": "No known failure pattern detected",
      "evidence": "All supported heuristic checks (malformed events, explicit errors, repeated calls, timeouts, and unmatched calls) passed without finding known failure patterns.",
      "recommendation": "No known issues detected under supported rules. Note that this does not guarantee overall task success.",
      "event_id": null
    }
  ],
  "timeline": [...]
}
```

---

## How to Test

Run the automated pytest test suite:

```bash
# From tools/agenttrace/
pytest -v
```

The test suite covers:
- Repeated identical tool calls ($\ge 3$) triggering High findings.
- Explicit error event detection (Critical and High).
- Error details on non-error events.
- Timeout heuristic detection on tool results (Medium).
- Unmatched tool calls on completed traces (Medium) vs. incomplete traces (no false alarms).
- Clean trace single informational result.
- Empty event arrays and boundary condition handling.
- Root schema and invalid type rejection (`ValueError`).
- Malformed non-object event resilience.
- Dictionary key order invariance for duplicate call normalization.
- Bounded evidence size ($\le 1,000$ characters).
- Duplicate and missing event ID validation.

---

## Known Limitations

- **Schema Mapping Required**: Input traces must follow the documented AgentTrace schema. AgentTrace does not automatically parse arbitrary proprietary logging formats without prior mapping.
- **Heuristic-Based**: Detections are deterministic heuristics (e.g., repetition count $\ge 3$, string-based timeout keywords). They do not constitute formal mathematical proof of root cause.
- **Offline / Post-Hoc**: AgentTrace reviews recorded traces after the run; it does not instrument live running agents or intercept network sockets.
- **Absence of Findings $\ne$ Guaranteed Success**: An `Info` finding indicates that no supported failure pattern was recognized, not that the agent achieved its broader semantic objective.

---

## Security & Privacy Considerations

- **Zero Data Transmission**: AgentTrace runs 100% locally on your machine. Traces are never sent to external servers or cloud APIs.
- **Untrusted Input Handling**: Uploaded or pasted JSON is parsed strictly as untrusted data using Python's standard `json` parser. Values are never executed with `eval`, `exec`, or shell processes.
- **Bounded Memory & Evidence**: Large trace strings and evidence snippets are truncated to 1,000 characters to prevent UI lag or memory exhaustion.
- **Zero Secrets**: No API keys, passwords, or credentials are required or stored.

---

## Future Improvements

- [ ] Add format converters for OpenTelemetry trace formats and popular framework logs.
- [ ] Support configurable heuristic thresholds (e.g., custom repetition threshold, custom timeout keywords).
- [ ] Add visualization for tool dependency call graphs and state transitions.
- [ ] Export diagnostic summaries to Markdown and HTML formats.

---

## License

*This project is contributed under the repository's open-source license.*
