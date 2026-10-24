# Securevantara

> Autonomous local security review & remediation agent combining deterministic Python AST checks with multi-provider LLM auditing and evidence validation.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Reviewing software for security vulnerabilities often forces developers into a difficult trade-off between noisy, inflexible static analysis tools and opaque cloud scanners that risk exposing proprietary code. Moreover, AI-generated security claims frequently hallucinate non-existent issues or line numbers.
- **Intended Users**: Business stakeholders, product and engineering teams, developers, security researchers, and authorized bug-bounty hunters assessing software repositories they own or have explicit written permission to test.

### Key Features
- **Multi-Stage Autonomous Agent Loop**: Discovers authorized sources, executes static AST tools, queries AI review models, cross-verifies line citations, plans contextual remediations, and computes executive risk metrics.
- **Deterministic AST Baseline**: Identifies risky dynamic execution calls (such as direct `eval()` and `exec()`) without external network calls or dependencies.
- **Multi-Provider LLM Auditing**: Supports local Ollama models (e.g. `gemma4:e4b`), Google Gemini models (e.g. `gemini-2.5-flash`), and offline mock engines with zero pip dependencies.
- **Strict Evidence Citation Validation**: Validates all model findings against actual source file lines; hallucinated line numbers or fabricated evidence strings are rejected.
- **Remediation & Patch Planning**: Provides concrete, safe mitigation guidance and alternative code patterns (such as `ast.literal_eval()`) for every validated finding.
- **Strict Scope & Privacy Boundaries**: Files are inspected in read-only mode and never executed. Reports are created with exclusive `0600` permissions.

---

## Technical Stack

- **Language & Runtime**: Python 3.9+ (Python 3.12 recommended; tested on Python 3.9.6 on macOS and 3.12 on Linux).
- **Agent Framework**: Google Agent Development Kit (ADK) (`google-adk>=2.13.0`) and lightweight multi-stage agent pipeline (`securevantara.agent`).
- **Models**:
  - Local: Ollama (`gemma4:e4b` default via loopback `127.0.0.1:11434`).
  - Cloud: Google Gemini (`gemini-2.5-flash` via standard REST API).
  - Test / CI: Offline deterministic mock provider.
- **External Engines (Optional)**: Xalgorix v4.6.159 subprocess adapter with bounded execution limits.

---

## Architecture & Data Flow

```text
[Authorized Source Snapshot]
          │
          ▼
┌────────────────────────────────────────────────────────┐
│               SecurityReviewAgent Loop                 │
│                                                        │
│  Stage 1: Discovery & Scope Authorization             │
│           (canonical path, symlink & size checks)      │
│                          │                             │
│  Stage 2: Deterministic AST Analysis (Tool)           │
│           (ast.parse, syntax tree walk)                │
│                          │                             │
│  Stage 3: Semantic AI Audit (Tool)                    │
│           (Ollama / Gemini / Mock)                     │
│                          │                             │
│  Stage 4: Triage & Evidence Verification               │
│           (exact line substring validation)            │
│                          │                             │
│  Stage 5: Remediation & Patch Planning                 │
│           (actionable mitigation & safe alternatives)  │
│                          │                             │
│  Stage 6: Synthesis & Risk Posture                     │
│           (severity metrics, SHA-256 provenance)       │
└────────────────────────────────────────────────────────┘
          │
          ▼
[Private JSON Report (mode 0600)]
```

The model receives no execution tools and cannot execute inspected code. Source code is treated strictly as untrusted data, never as prompt instructions. All model-suggested findings remain marked `unverified`.

---

## Prerequisites

- **Python 3.9+** (Python 3.12 recommended).
- **Ollama** (optional, if using `--provider ollama`): running locally on `http://127.0.0.1:11434`.
- **Gemini API Key** (optional, if using `--provider gemini`): export `GEMINI_API_KEY`.
- No third-party pip packages are required for core operations.

---

## Installation & Setup

1. **Navigate to the agent directory:**
   ```bash
   cd agents/securevantara
   ```

2. **Set up the virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   mkdir -p reports
   ```

3. **Configure Environment Variables (Optional):**
   ```bash
   cp .env.example .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | No (only for Gemini) | *None* | Google Gemini API key for `--provider gemini` |
| `XALGORIX_LLM_PROVIDER` | No | `ollama` | Optional Xalgorix engine LLM provider |
| `XALGORIX_LLM` | No | `gemma4:e4b` | Model name for optional Xalgorix adapter |
| `XALGORIX_API_BASE` | No | `http://127.0.0.1:11434` | Endpoint for optional Xalgorix engine |

---

## How to Run

### 1. Run with Google Agent Development Kit (ADK)

Securevantara exposes a first-class `root_agent` equipped with AST scanning, source reading, citation verification, and remediation tools:

```bash
# Set your Gemini API key:
export GEMINI_API_KEY="your-api-key"

# Launch the interactive local ADK Web UI (visualize reasoning, chat, tool invocations):
adk web agents/

# Run a single turn via ADK CLI:
adk run agents/securevantara "Review examples/source for security vulnerabilities"

# Or run programmatic ADK execution via Securevantara CLI:
python -m securevantara adk --query "Audit examples/source for security issues" --report reports/adk-report.json
```

### 2. Autonomous Security Review Agent (Local & Cloud)

Run the multi-stage agent pipeline over an authorized codebase snapshot:

```bash
# Using offline mock provider (instant, zero network):
python -m securevantara agent \
  --source examples/source --scope examples/source --authorized \
  --provider mock --report reports/agent-report-1.json

# Using local Ollama model (gemma4:e4b):
python -m securevantara agent \
  --source examples/source --scope examples/source --authorized \
  --provider ollama --model gemma4:e4b --timeout 120 \
  --report reports/agent-ollama-1.json

# Using Google Gemini:
export GEMINI_API_KEY="your-api-key"
python -m securevantara agent \
  --source examples/source --scope examples/source --authorized \
  --provider gemini --model gemini-2.5-flash \
  --report reports/agent-gemini-1.json
```

### 2. Run Built-in AST Checks Only

Run deterministic static checks with no LLM inference:

```bash
python -m securevantara check \
  --source examples/source --scope examples/source --authorized \
  --report reports/check-1.json
```

### 3. Run Single-Shot Ollama Review

```bash
python -m securevantara review \
  --source examples/source --scope examples/source --authorized \
  --model gemma4:e4b --timeout 120 \
  --report reports/review-1.json
```

### 4. Docker Execution

Run tests or check within a hardened read-only container:

```bash
docker build -t securevantara:local .
docker build --target tests -t securevantara-tests .
docker run --rm --network none --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 64 --memory 256m --cpus 1 \
  securevantara-tests
```

### 5. Optional Xalgorix Adapter (Partial)

```bash
python -m securevantara xalgorix-info --report reports/xalgorix-info-1.json
```

---

## Example Input & Output

### Example Input (`examples/source/sample.py`)
```python
"""Synthetic review fixture. Never run this function with untrusted input."""

def calculate(expression):
    # Deliberate finding for the local smoke test; not production application code.
    return eval(expression)
```

### Example Output (`reports/agent-report.json`)
```json
{
  "schema_version": "1.0",
  "operation": "agent",
  "source": "examples/source",
  "scope": "examples/source",
  "authorized": true,
  "agent": {
    "name": "Securevantara Security Review Agent",
    "version": "1.0.0",
    "provider": "mock",
    "model": "mock-engine",
    "stages_executed": [
      "discovery",
      "static_analysis",
      "semantic_audit",
      "triage_verification",
      "remediation_planning",
      "synthesis"
    ],
    "metrics": {
      "files_reviewed": 1,
      "files_skipped": 0,
      "total_findings": 2,
      "severity_counts": {
        "critical": 0,
        "high": 1,
        "medium": 0,
        "low": 0,
        "info": 1
      },
      "risk_posture": "High"
    },
    "reviewed_files": {
      "sample.py": "72ca979836865190d8de13a7bed6ff594d2c99043c06b6852251c576fa2ecdbe"
    }
  },
  "findings": [
    {
      "id": "16155e652169a48ba4f930bb6a7979d47aeced5dfc1e7f63bb34f16aee5b9390",
      "rule": "python.dynamic-eval",
      "title": "Dynamic Python execution",
      "severity": "info",
      "status": "needs-review",
      "kind": "source-review",
      "path": "sample.py",
      "line": 6,
      "evidence": "eval(expression)",
      "provenance": [{"engine": "securevantara-ast", "rule": "python.dynamic-eval"}],
      "remediation": "Avoid eval() with untrusted input. Use ast.literal_eval() to safely parse Python literals (strings, numbers, tuples, lists, dicts, booleans, None), or use json.loads() for structured JSON.",
      "safer_alternative": "ast.literal_eval(expression)"
    }
  ],
  "errors": [],
  "exit_status": 0
}
```

---

## Reports, Finding Schema & Statuses

Each normalized finding conforms to the following schema:

| Field | Meaning |
| :--- | :--- |
| `id` | SHA-256 of engine rule, relative path, line and exact evidence |
| `rule`, `title` | Detector identity and concise summary |
| `severity` | `info` / `low` / `medium` / `high` / `critical` |
| `status` | `needs-review` / `unverified` (confirmed is reserved for future runtime verification) |
| `kind` | `source-review` (never dynamic penetration testing) |
| `path`, `line` | Relative source location and 1-based line number |
| `evidence` | Exact source fragment on the cited line |
| `provenance` | List of contributing detectors, models, or engines |
| `remediation` | Contextual mitigation advice for the detected pattern |
| `safer_alternative` | Recommended safe alternative code snippet |

---

## How to Test

Run the full automated test suite (42 unit tests covering ADK tools, lifecycle stages, AST parsing, and model adapters):

```bash
cd agents/securevantara
python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=/tmp/securevantara-pycache python3 -m compileall -q securevantara tests
```

From repository root:
```bash
git diff --check
```

---

## Known Limitations

- **Source Scope Limits**: Bounds source inspection to at most 10 files, 12,000 bytes per file, and 24,000 source characters total per batch.
- **Model Variability**: AI-generated suggestions vary across models and temperatures. Model output is verified for exact source line citations, but semantic soundness still requires human review.
- **No Autonomous Exploitation**: Securevantara does not exploit systems, patch live code autonomously, or submit external bounty reports.
- **Symlinks & Special Files**: Symlinked directories and special device files fail closed to prevent accidental scope escape.

---

## Security & Privacy Considerations

- **Secrets Handling**: Zero credentials or private `.env` files are tracked in git. API keys (such as `GEMINI_API_KEY`) are read from memory only and never serialized to reports.
- **Data Privacy**: Local mode (`--provider ollama`) communicates exclusively over loopback (`127.0.0.1:11434`). Source code never leaves your local machine unless you explicitly choose a cloud provider.
- **Safety Boundaries**: The agent inspects code in read-only mode and never invokes `eval()`, `exec()`, or executes child processes on inspected source code.
- **Exclusive Report Permissions**: Output reports are created with mode `0600` (read/write only by file owner) using `O_EXCL` creation to prevent overwriting or following malicious symlinks.

---

## Roadmap & Future Improvements

- [x] Autonomous multi-stage review agent lifecycle
- [x] Multi-provider LLM support (Ollama + Google Gemini + Mock)
- [x] Contextual remediation and safer alternative code suggestions
- [x] Strict evidence citation validation against source lines
- [ ] Add Semgrep, Bandit, and Ruff static analyzer tool adapters
- [ ] Support streaming large repositories with dynamic chunking
- [ ] Interactive terminal dashboard for triaging findings
- [ ] HTML / PDF executive summary export

---

## License

Contributed under the parent repository's MIT License. Optional external tools retain their own respective licenses. See [VERIFICATION.md](VERIFICATION.md) for actual test run notes.
