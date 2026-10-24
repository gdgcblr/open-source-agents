# AgentRelay — Evidence-Driven AI Engineering Investigation Platform

> An evidence-grounded AI engineering investigation platform that connects pre-deployment code reviews with post-deployment production incident diagnosis without hallucinations, unnecessary model calls, or false causal claims.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Modern software engineering teams suffer from disconnected investigation silos. Pre-deployment code reviews miss subtle regressions, while post-deployment incident triage struggles to link production anomalies (logs, metrics, traces) back to the responsible pull requests and diffs. Furthermore, naive LLM-based investigation tools hallucinate non-existent evidence, claim causal certainty from mere temporal proximity, and waste tokens on tasks that deterministic static analysis solves faster and with 100% precision.
- **Intended Users**: Site Reliability Engineers (SREs), software engineers, security auditors, and release managers seeking reproducible, evidence-backed diagnostic reports.

### Key Features
- **Deterministic Pre-Deployment Code Review**: Unified diff parsing with zero external dependencies. Detects hardcoded secrets, SQL injection vectors, unsafe shell commands, insecure deserialization, silent exception suppression, and missing test coverage updates.
- **Telemetry-Correlated Incident Investigation**: Ingests production logs, time-series metrics, traces, and deployment manifests. Clusters error signatures, detects metric spikes, and produces ranked root-cause hypotheses with attached supporting and contradicting evidence citations.
- **Cross-Workflow Correlation (Without False Causality)**: Links code review findings with incident deployments using exact commit SHAs and service identifiers. Explicitly enforces the invariant that matching identifiers and temporal proximity are circumstantial associations, **never** definitive proof of causation.
- **Token-Efficient Model Policy**: Pure deterministic execution for parsing, validation, metric calculations, diff analysis, and correlation (0 LLM calls, 0 token cost). Bounded semantic reasoning is invoked only for ambiguous context-dependent reasoning when explicitly enabled and configured.
- **Evidence-First Guardrails & Security**: Enforces evidence-ID integrity, rejects fabricated citations, redacts credentials, flags adversarial prompt-injection patterns in untrusted logs, and requires multiple corroborating citations for high-confidence claims.
- **Offline Deterministic Evaluation Suite**: 100% reproducible evaluation harness covering precision, recall, citation validity, abstention accuracy, and adversarial prompt-injection resistance without requiring third-party API keys.

---

## Technical Stack

- **Language & Runtime**: Python 3.9+ (tested on Python 3.9, 3.11, and 3.12).
- **Core Engine**: Pure Python standard library (zero external dependencies required for offline core, CLI, unit tests, and evaluation suite).
- **Optional Model Integrations**: Google Gemini API / Google Agent Development Kit (ADK) / OpenAI API via structured HTTP clients.
- **Testing & Evaluation**: Python `unittest` (standard library) and optional `pytest`.

---

## Architecture & Data Flow

```
                     +---------------------------------------+
                     |    Input Data (Diff / Incident JSON)  |
                     +---------------------------------------+
                                         |
                                         v
                     +---------------------------------------+
                     |   Sanitization & Secret Redaction     |
                     |  (inspect_untrusted_text, redact)     |
                     +---------------------------------------+
                                         |
                                         v
                     +---------------------------------------+
                     |    Deterministic Analysis Pipeline    |
                     |  - Unified diff parser & risk rules   |
                     |  - Metric surge & log error cluster   |
                     |  - EvidenceRecord store indexing      |
                     +---------------------------------------+
                                         |
             +---------------------------+---------------------------+
             |                                                       |
             v                                                       v
 [Model Policy: Disabled/Offline]                      [Model Policy: Enabled & Ambiguous]
  Return deterministic report                          - Bounded prompt with redacted diff
  (0 model calls, 0 tokens)                            - Structured output schema validation
                                                       - Citation verification against store
                                                       - Graceful fallback on API failure
             |                                                       |
             +---------------------------+---------------------------+
                                         |
                                         v
                     +---------------------------------------+
                     |       Deterministic Guardrails        |
                     |  - Evidence-ID reference integrity    |
                     |  - Multi-citation for high confidence |
                     |  - Reject hallucinated citations      |
                     +---------------------------------------+
                                         |
                                         v
                     +---------------------------------------+
                     | Cross-Workflow Correlation (Optional) |
                     |  - Matches commit SHA / deployment ID |
                     |  - Flags service & temporal conflicts |
                     |  - Non-causal association disclaimer  |
                     +---------------------------------------+
                                         |
                                         v
                     +---------------------------------------+
                     |    Terminal Text / Machine JSON       |
                     +---------------------------------------+
```

---

## Prerequisites

- Python 3.9 or higher.
- Git (for generating unified diff patches).
- No API keys are required for core deterministic review, incident investigation, correlation, evaluations, and tests.

---

## Installation & Setup

1. **Navigate to the tool directory:**
   ```bash
   cd tools/agentrelay
   ```

2. **Verify runtime environment:**
   The core engine uses Python standard library modules (`dataclasses`, `typing`, `json`, `re`, `urllib`).
   No external packages need to be installed for offline operation.

   *(Optional) To install optional development dependencies (e.g. pytest):*
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables (Optional):**
   ```bash
   cp .env.example .env
   ```
   By default, `AGENTRELAY_OFFLINE_MODE=true`. Leave this setting as-is for 100% offline execution.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `AGENTRELAY_OFFLINE_MODE` | No | `true` | When true, disables all outbound model network calls |
| `AGENTRELAY_MODEL_PROVIDER` | No | `offline` | Provider identifier (`offline`, `gemini`, `mock`) |
| `GEMINI_API_KEY` | No | *None* | Google Gemini API key (optional; only needed if offline mode is disabled) |
| `AGENTRELAY_MODEL_NAME` | No | `gemini-2.5-flash` | Model identifier for optional semantic reasoning |
| `AGENTRELAY_MAX_TOKENS` | No | `2048` | Maximum output tokens for model requests |
| `AGENTRELAY_TEMPERATURE` | No | `0.0` | Sampling temperature (enforces deterministic model outputs) |
| `AGENTRELAY_REDACT_SECRETS` | No | `true` | Automatically redact API keys, tokens, and credentials |
| `LOG_LEVEL` | No | `info` | Logging verbosity (`debug`, `info`, `warn`, `error`) |

---

## How to Run

AgentRelay provides a unified CLI with subcommands for review, investigation, correlation, evaluation, and safety validation:

### 1. Pre-Deployment Code Review
Analyze a unified git diff for concrete vulnerabilities, credentials, and test coverage omissions:
```bash
python3 -m agentrelay.cli review --diff examples/sample_diff.patch
```

Output formatted JSON:
```bash
python3 -m agentrelay.cli review --diff examples/sample_diff.patch --json
```

Pipe directly from `git diff`:
```bash
git diff main | python3 -m agentrelay.cli review --diff -
```

### 2. Production Incident Investigation
Analyze simulated or exported incident telemetry (logs, metrics, traces, deployments):
```bash
python3 -m agentrelay.cli investigate --incident examples/incident.json
```

### 3. Cross-Workflow Correlation
Connect pre-deployment review findings to production incident events using commit SHAs and deployment IDs:
```bash
# Generate review report with commit metadata
python3 -m agentrelay.cli review --diff examples/sample_diff.patch --commit a7b9c1d --service checkout-service --json > /tmp/review.json

# Correlate review report with production incident
python3 -m agentrelay.cli correlate --review /tmp/review.json --incident examples/incident.json
```

### 4. Deterministic Report Validation
Validate that a report satisfies structural integrity and valid evidence citations:
```bash
python3 -m agentrelay.cli validate --evidence examples/evidence.json --report /tmp/review.json
```

### 5. Run Offline Evaluation Suite
Execute the deterministic evaluation benchmark across positive, negative, adversarial, and abstention test cases:
```bash
python3 -m agentrelay.cli evaluate
```
Or directly run the standalone evaluation runner:
```bash
python3 evals/run_evals.py
```

### 6. Interactive Web Dashboard
Launch the zero-dependency interactive investigation dashboard in your browser:
```bash
python3 -m agentrelay.cli dashboard
# Or with specific port:
python3 -m agentrelay.cli dashboard --port 8080
```
This provides an interactive UI for pasting patches, running incident telemetry triage with SVG surge charts, linking cross-workflow correlations, and running offline evaluation benchmarks.


---

## Example Input & Output

### Example: Running Code Review
**Command**:
```bash
python3 -m agentrelay.cli review --diff examples/sample_diff.patch
```

**Output**:
```
======================================================================
 AgentRelay — PRE-DEPLOYMENT CODE REVIEW
======================================================================
Summary: Deterministic code review inspected 1 file(s). Found 4 potential issue(s) across 4 evidence citation(s).

--- Findings (4) ---
[1] [CRITICAL] (Confidence: medium) [Heuristic] Hardcoded Secret or Token detected in services/checkout/payment_processor.py:20
    Evidence: diff-ev-001
    Explanation: A hardcoded secret, token, or API key was detected in added lines. Committing credentials poses immediate security exposure.
    Next Action: Move credential to environment variables or secret manager immediately; rotate exposed keys.

[2] [HIGH] (Confidence: medium) [Heuristic] Unparameterized SQL Query detected in services/checkout/payment_processor.py:24
    Evidence: diff-ev-002
    Explanation: Dynamic SQL construction using string formatting or concatenation detected. This creates an unescaped SQL injection vector.
    Next Action: Use parameterized queries (e.g., cursor.execute(query, (param,))) or a type-safe ORM query builder.

[3] [HIGH] (Confidence: medium) [Heuristic] Insecure Deserialization detected in services/checkout/payment_processor.py:30
    Evidence: diff-ev-003
    Explanation: Insecure deserialization using pickle or unsafe YAML loader detected. Unpickling untrusted byte streams allows arbitrary remote code execution.
    Next Action: Use safe serialization formats like JSON, or yaml.safe_load. Never unpickle untrusted data.

[4] [MEDIUM] (Confidence: low) Production code modified without accompanying unit or integration tests
    Evidence: diff-ev-004
    Explanation: 1 production file(s) changed without corresponding modifications in test files, increasing regression risk.
    Next Action: Add regression and edge-case unit tests covering the modified functions.

--- Unknowns & Boundaries ---
  • Static regex heuristics cannot verify dynamic runtime sanitization or type invariants.
  • Full architectural impact cannot be determined from diff alone without complete repository context.

--- Recommended Actions ---
  → Address critical and high severity findings before deploying code to production.
======================================================================
```

### Example: Cross-Workflow Correlation
**Command**:
```bash
python3 -m agentrelay.cli correlate --review /tmp/review.json --incident examples/incident.json
```

**Output**:
```
======================================================================
 AgentRelay — Cross-Workflow Correlation Report
======================================================================
Summary: Correlation completed: Established 4 association(s) between code review and incident INC-8921. (All associations are non-causal hypotheses requiring verification).

--- Linked Associations (4) ---
[1] [EXACT_COMMIT_MATCH] Review finding: '[Heuristic] Hardcoded Secret or Token detected in services/checkout/payment_processor.py:20'
    Basis: Code review commit SHA 'a7b9c1d' exactly matches deployment 'dep-902' deployed to service 'checkout-service'.
    Caution: ASSOCIATION ONLY: Matching commit SHA proves that this code was deployed, NOT that this specific code change caused the incident.

IMPORTANT: DISCLAIMER: Correlated events reflect temporal, service, or identifier overlap. They are hypotheses requiring diagnostic verification, not verified causal proof.
======================================================================
```

---

## Token Efficiency & Model Policy

AgentRelay enforces a strict, centralized model policy (`agentrelay/model_policy.py`):

1. **Zero LLM Calls for Deterministic Tasks**:
   - Diff parsing and line extraction
   - Regex-based risk checks (secrets, injection, unsafe deserialization)
   - Metric time-series anomaly calculations
   - Error log clustering and signature deduplication
   - Commit SHA and deployment ID exact matching
   - Schema and citation-ID verification
2. **When the Optional Model is Invoked**:
   - Only when `AGENTRELAY_OFFLINE_MODE=false`, valid provider credentials exist, and semantic reasoning is explicitly enabled (`--semantic`).
   - Used exclusively for semantic ambiguity analysis, context-dependent multi-file interactions, and comparing competing hypotheses.
3. **Guardrails on Model Responses**:
   - Model outputs are treated as untrusted data.
   - Any claim citing a nonexistent evidence ID is rejected and stripped.
   - High-confidence claims require at least 2 distinct verified citations.
   - In case of model timeout or schema failure, the system falls back to the deterministic baseline with transparent execution metadata.
4. **Honest Accounting**:
   - Measured token usage is reported directly from provider APIs.
   - In offline or mock mode, token usage is explicitly marked `is_measured=False`. Token counts and costs are never fabricated.

---

## Non-Causality Guarantee

A fundamental architectural principle of AgentRelay is distinguishing **correlation** from **causation**:
- A commit SHA matching a deployment record proves that the commit was deployed. It does **not** prove that changes in that commit caused the incident.
- Temporal proximity (e.g. an incident starting 5 minutes after a release) is circumstantial context, not definitive proof of culpability.
- The system always sets `is_causal_proof = False` on every correlation link, explicitly attaches warning notes, and produces alternative hypotheses (such as downstream infrastructure exhaustion or external network failure).

---

## How to Test

Run the complete unit test suite and offline evaluations:

```bash
# Run all unit tests (standard library unittest)
python3 -m unittest discover -s tests -p "test_*.py" -v

# Run offline evaluation suite
python3 evals/run_evals.py
```

### Evaluation Benchmark Results
The offline evaluation suite runs against deterministic fixtures in `evals/test_cases.json`:
- **Total Test Cases**: 8
- **Pass Rate**: 100.0%
- **Evidence Citation Validity Rate**: 100.0%
- **Abstention Accuracy**: 100.0% (abtains on insufficient telemetry)
- **Prompt Injection Resistance**: 100.0% (flags adversarial instructions in untrusted logs)
- **Mean Suite Latency**: < 5 ms

---

## Known Limitations

- **Heuristic Pattern Matching**: Deterministic static checks detect known syntactic risk patterns (e.g. unparameterized SQL f-strings, bare `except: pass`). They cannot verify complex runtime control flow or type invariants without dynamic testing.
- **Diff-Level Visibility**: Pre-deployment review analyzes the supplied patch. Without full repository AST indexing, imported utility functions that perform out-of-band sanitization are unknown.
- **Simulated Demonstration Incident**: The provided `examples/incident.json` is synthetic data created for reproducible local demonstration and does not represent live production systems.
- **Prompt Injection Detection**: Regex-based prompt-injection inspection detects known prompt override phrases. Because adversarial prompts evolve, all untrusted evidence text is treated strictly as data and never concatenated into unconstrained prompt templates.
