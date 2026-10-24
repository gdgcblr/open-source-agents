# Jarvis — A PR Review Agent

> An autonomous AI agent for security audit, 5-layer guardrail defense, code quality review, and automated Conventional Pull Request description generation from Git diffs, powered by a Dual-Engine architecture (Local Gemma 2 + Cloud Gemini).

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Open-source maintainers and developers face severe review fatigue. Code reviews are bogged down by manual checks for basic hygiene (leaked credentials, hardcoded keys, missing unit tests, unpinned dependencies) and writing detailed PR descriptions. Developers often submit PRs with empty or vague descriptions, making peer review tedious and increasing the risk of accidental secret leaks reaching production.
- **Intended Users**: Software engineers, open-source contributors, devops engineers, and tech leads who want instant pre-commit or pre-merge feedback, deterministic security guardrails, and automated PR documentation directly in their terminal or CI/CD pipelines.

### Key Features
- **5-Layer Guardrail Architecture**: Defense-in-depth security that combines deterministic pre-LLM secret scanning, anti-pattern execution blocking, noise filtering, and policy enforcement overrides.
- **Dual-Engine Architecture**:
  - **Local Gemma 2 / Privacy Engine**: Scans code diffs locally and offline for sensitive secrets, credentials, and syntax anti-patterns without sending private code to the cloud.
  - **Cloud Gemini 2.5 / Architect Engine**: Analyzes architectural impact, evaluates breaking changes, and generates complete Conventional PR summaries with verification checklists.
  - **Zero-Credential Mock Engine**: Built-in deterministic mock provider for instant CI/CD test runs without API keys.
- **Deterministic Secret & Vulnerability Scan**: Instant pre-LLM detection of leaked API keys (Google AI, GitHub PATs, OpenAI, AWS, Stripe), committed `.env` files, and dangerous patterns (`eval()`, `exec()`, raw SQL string formatting).
- **Dual Interface (CLI & REST API)**: Execute as a fast terminal tool (`python main.py`) or run as a standalone FastAPI service (`python main.py --serve`) with interactive Swagger documentation.
- **Strict Risk Scoring & Verdicts**: Assigns a risk score (0-100) and authoritative review verdicts (`APPROVE`, `REQUEST_CHANGES`, `COMMENT`).

---

## 🛡️ 5-Layer Guardrail Architecture

Jarvis is architected with **Defense-in-Depth**. Rather than relying solely on probabilistic LLMs which can hallucinate or miss obscure vulnerabilities, Jarvis enforces 5 distinct guardrail tiers:

```
[ Incoming Git Diff ]
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Layer 1: Context & DOS Guard                           │
│ Strips lockfiles (package-lock.json), minified assets, │
│ and binary blobs to protect LLM context windows.       │
└─────────────────────────┬──────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────┐
│ Layer 2: Deterministic Secret Shield (Pre-LLM)         │
│ Zero-hallucination regex audit for Google AI keys,     │
│ GitHub PATs, AWS/Stripe tokens, & committed .env files │
└─────────────────────────┬──────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────┐
│ Layer 3: Code Injection & Anti-Pattern Guard           │
│ Catches arbitrary code execution risks: eval(), exec(),│
│ subprocess(shell=True), and raw SQL string injections. │
└─────────────────────────┬──────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────┐
│ Layer 4: Air-Gapped Privacy Guard (Local Gemma 2)      │
│ In offline mode, diffs are reviewed 100% locally on-box│
│ using Ollama (gemma2:2b). Zero bytes leave your machine│
└─────────────────────────┬──────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────┐
│ Layer 5: Authoritative Verdict Escalation Guard        │
│ The LLM is forbidden from approving unsafe code:       │
│ If Critical issues exist, verdict is FORCE-OVERRIDDEN  │
│ to REQUEST_CHANGES and risk score escalated to >= 85.  │
└────────────────────────────────────────────────────────┘
```

| Guardrail Layer | Category | Enforcement Mechanism |
| :--- | :--- | :--- |
| **Layer 1: Context & DOS Guard** | Input Hygiene | Automatically filters noise diffs (`package-lock.json`, minified bundles, images) before tokenization in `git_utils.py`. |
| **Layer 2: Secret Shield (Pre-LLM)** | Data Security | Pre-LLM static regex audit catching Google AI keys, GitHub PATs, AWS secrets, and private keys in `security_scanner.py`. |
| **Layer 3: Anti-Pattern Guard** | Vulnerability Defense | Scans for remote code execution anti-patterns (`eval()`, `exec()`, `shell=True`, SQL injection) before LLM synthesis. |
| **Layer 4: Air-Gapped Privacy Guard** | Data Leak Prevention | Local offline execution via Google Gemma 2 (`gemma2:2b`) ensuring proprietary code never leaves the developer's laptop. |
| **Layer 5: Verdict Escalation Guard** | Policy & Output Safety | Deterministic rule in `agent.py` overriding LLM output: if critical security flaws exist, verdict is forcibly set to `REQUEST_CHANGES`. |

---

## High-Level Design (HLD)

The High-Level Design follows a modular, dual-tier inspection pipeline designed for high security, low latency, and framework independence:

```mermaid
flowchart TD
    User["Developer / Contributor"] -->|git diff / CLI / REST API| Ingest["Ingestion & Chunking Layer"]
    Ingest --> NoiseFilter["Noise Filter (strips lockfiles, minified assets, binaries)"]
    
    subgraph Privacy_Tier["Privacy & Security Layer (Offline)"]
        NoiseFilter --> SecScan["Deterministic Secret Scanner (Regex & Heuristics)"]
        SecScan --> LocalGemma["Local Gemma 2 via Ollama (Air-gapped Review)"]
    end
    
    subgraph Architect_Tier["Cloud / Reasoning Tier"]
        NoiseFilter --> CloudGemini["Google Gemini 2.5 Flash / Pro (Deep Reasoning)"]
        CloudGemini --> PRSynth["Conventional PR Synthesizer"]
    end
    
    SecScan --> Aggregator["Finding Aggregator & Risk Engine"]
    LocalGemma --> Aggregator
    CloudGemini --> Aggregator
    PRSynth --> Aggregator
    
    Aggregator --> Output["Review Report & Markdown PR Description"]
    Output --> CLI_Out["Terminal CLI / pr_description.md"]
    Output --> API_Out["FastAPI REST Endpoints (/docs)"]
```

---

## Low-Level Design (LLD)

The Low-Level Design decomposes the agent into discrete, single-responsibility modules:

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer
    participant CLI as main.py (CLI / FastAPI)
    participant Agent as GitPRReviewAgent (agent.py)
    participant Git as git_utils.py
    participant Sec as security_scanner.py
    participant LLM as llm_client.py (Gemini / Gemma / Mock)
    
    Dev->>CLI: python main.py --branch main
    CLI->>Agent: review_repository(repo_path, base_branch)
    Agent->>Git: get_git_diff(base_branch)
    Git-->>Agent: (filtered_diff, stats)
    
    par Security Pre-Scan
        Agent->>Sec: scan_diff_for_security_issues(diff)
        Sec-->>Agent: List[ReviewIssue] (CRITICAL, WARNING)
    and Model Reasoning
        Agent->>LLM: review_diff(diff, stats)
        LLM-->>Agent: JSON (pr_summary, issues, risk_score, verdict)
    end
    
    Agent->>Agent: Merge & deduplicate issues
    Agent->>Agent: Escalate risk score if secrets detected (verdict=REQUEST_CHANGES)
    Agent->>Agent: generate_markdown_pr(report)
    Agent-->>CLI: ReviewReport + Markdown String
    CLI-->>Dev: Formatted Terminal Summary / pr_description.md
```

### Component Details
1. **`git_utils.py`**: Interacts with the local git repository using subprocess without `shell=True`. Filters out high-churn generated files (`package-lock.json`, minified bundles, images) and computes changed line metrics.
2. **`security_scanner.py`**: Pure Python regex engine with zero external dependencies. Pre-screens diffs against high-entropy API key patterns and dangerous code execution calls (`eval`, `exec`, `subprocess.Popen(..., shell=True)`).
3. **`llm_client.py`**: Provider abstraction wrapping `google-genai` (Gemini 2.5 Flash / 1.5 Flash), local Ollama HTTP API (`gemma2:2b`), and `MockProvider`. Enforces structured JSON output matching Pydantic schemas.
4. **`agent.py`**: Coordinates the pipeline, aggregates findings, enforces verdict rules (any critical secret automatically overrides verdict to `REQUEST_CHANGES` and sets risk score $\ge 85$), and generates clean GitHub Flavored Markdown.
5. **`models.py`**: Pydantic v2 schemas defining `ReviewIssue`, `PullRequestSummary`, `ReviewReport`, and `ReviewRequest`.
6. **`main.py`**: Unified entrypoint supporting CLI arguments (`--branch`, `--staged`, `--diff-file`, `--json`, `--output`) and FastAPI web server mode (`--serve`).

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.9 or higher (tested on Python 3.9 and 3.12)
- Git 2.30+ installed
- *(Optional for cloud inference)*: A Google Gemini API key from [Google AI Studio](https://aistudio.google.com/)
- *(Optional for offline local inference)*: [Ollama](https://ollama.com/) with `ollama run gemma2:2b`

---

## Installation & Setup

1. **Navigate to the agent directory:**
   ```bash
   cd agents/git-pr-review-agent
   ```

2. **Set up a virtual environment and install dependencies:**
   ```bash
   python -m venv .venv

   # On Linux/macOS:
   source .venv/bin/activate

   # On Windows:
   .venv\Scripts\activate

   pip install -r requirements.txt
   ```

3. **Configure Environment Variables (Optional):**
   Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
   Add your Gemini API key if using cloud inference, or leave blank to automatically use local Ollama (`gemma2:2b`) or Mock mode:
   ```bash
   GEMINI_API_KEY=AIzaSy...
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | No | *None* | Google Gemini API key for cloud model reasoning |
| `LLM_PROVIDER` | No | `auto` | Preferred provider: `gemini`, `ollama`, or `mock` |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Model identifier (`gemini-2.5-flash`, `gemma2:2b`, etc.) |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama HTTP endpoint for local offline inference |
| `PORT` | No | `8000` | Port for the FastAPI server when running `--serve` |
| `HOST` | No | `0.0.0.0` | Host bind address for the FastAPI server |

---

## How to Run

### Option 1: Review Local Git Changes (CLI)

```bash
# Review current unstaged and staged changes in your git repository:
python main.py

# Review against a specific target branch (e.g. main):
python main.py --branch main

# Review only staged changes:
python main.py --staged

# Save generated PR description directly to a markdown file:
python main.py --output pr_description.md

# Output machine-readable JSON for CI/CD pipelines:
python main.py --json
```

### Option 2: Review from a Patch File or Stdin

```bash
# Review a pre-existing diff/patch file:
python main.py --diff-file sample.patch

# Pipe directly from git:
git diff main | python main.py
```

### Option 3: Offline Local Execution with Google Gemma 2

```bash
# Force using local Gemma 2 via Ollama (100% private, no internet needed):
python main.py --provider ollama --model gemma2:2b
```

### Option 4: Zero-Credential Mock Mode (for CI/CD testing)

```bash
python main.py --provider mock
```

### Option 5: Run as a REST API Server

```bash
python main.py --serve --port 8000
```
Open [http://localhost:8000/docs](http://localhost:8000/docs) in your browser to access the interactive Swagger UI.

---

## Example Input & Output

### Example Input Diff
```diff
diff --git a/auth/token_manager.py b/auth/token_manager.py
new file mode 100644
--- /dev/null
+++ b/auth/token_manager.py
@@ -0,0 +1,5 @@
+import os
+
+GEMINI_KEY = "AIzaSyB1234567890abcdef1234567890abcdef"
+def verify_token(raw_input):
+    return eval(raw_input)
```

### Example Terminal / Markdown Output
```markdown
# feat(auth): add token manager implementation

> 🤖 *Automated review and PR description generated by **Git PR Review Agent**.*

## Summary
Added initial token manager module under auth/token_manager.py with key definitions.

## Review Overview
- **Verdict**: 🔴 **CHANGES REQUESTED**
- **Risk Score**: `100/100`
- **Model Used**: `Gemini (gemini-2.5-flash)`
- **Changes**: `1 files` (+5 / -0)

## 🔍 Code Review Findings
### 🚨 [CRITICAL] Google API / Gemini Secret Key
**File**: `auth/token_manager.py:L3` | **Category**: `security`
Potential secret detected on line 3 of auth/token_manager.py.
> **Suggestion**: Remove this API key immediately! Use environment variables or a secret manager.

### 🚨 [CRITICAL] Arbitrary Code Execution via eval()
**File**: `auth/token_manager.py:L5` | **Category**: `security`
Dangerous security anti-pattern found: return eval(raw_input)
> **Suggestion**: eval() allows arbitrary code execution. Refactor to use safe parsing.

## 📋 Verification Checklist
- [ ] Remove hardcoded credentials from source code
- [ ] Refactor eval() to safe ast.literal_eval or json parsing
- [ ] Run automated test suite: pytest
```

---

## How to Test

Run the comprehensive unit test suite:

```bash
pytest -v
```

The test suite validates:
1. Static security scanner against leaked API keys, tokens, and code smells.
2. Safe diff chunking and lockfile filtering.
3. Multi-provider fallbacks and mock generation.
4. Risk score escalation on critical findings.
5. Markdown PR generation formatting.
6. FastAPI health and review REST endpoints.

---

## Known Limitations

- **Binary & Large Asset Diffs**: Non-text assets (images, compiled binaries) are filtered out to conserve token limits and avoid parsing errors.
- **Very Large Diffs**: Single diffs exceeding 35,000 characters are safely truncated to fit within model context windows without crashing.
- **Local Ollama Speed**: When running offline with local `gemma2:2b`, generation latency depends on local CPU/GPU hardware.

---

## Security & Privacy Considerations

- **Zero Secrets Tracked**: `.env` and secret patterns are in `.gitignore`. The static scanner actively blocks committed `.env` files.
- **Air-Gapped Operation**: With `--provider ollama` or `--provider mock`, zero code diffs or telemetry are transmitted outside the local machine.
- **Safe Command Execution**: Git commands are run with explicit argument arrays without `shell=True` to prevent command injection.

---

## Future Improvements

- [ ] GitHub Actions workflow integration for automated PR review comments.
- [ ] Multi-turn interactive discussion with the agent on specific review findings.
- [ ] Support for AST-based Python semantic diffing.

---

## License

*This project is contributed under the repository's open-source license.*
