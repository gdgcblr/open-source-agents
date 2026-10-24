# Autonomous DevOps Incident Responder

> A Gemini-powered Site Reliability Engineering (SRE) agent that autonomously detects, investigates, classifies severity, remediates, and verifies microservice incidents within a deterministic simulated environment.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Modern distributed microservice incidents require rapid root-cause analysis, accurate severity triage, and safe remediation. In high-stress outage scenarios, manual triage is prone to delayed escalation, risky speculative fixes (such as blind restart loops during database outages), and inconsistent severity classification.
- **Intended Users**: DevOps engineers, Site Reliability Engineers (SREs), platform engineering teams, and AI agent developers building autonomous operations tools.

### Key Features
- **Impact-Driven Severity Assessment**: Deterministically classifies incidents into `SEV-1` (Critical), `SEV-2` (High), `SEV-3` (Moderate), and `SEV-4` (Low) with mapped operational response priorities (`P1-CRITICAL-URGENT` to `P4-LOW`).
- **Dynamic Reasoning with Gemini Function Calling**: Uses the official Google Gen AI SDK (`google-genai`) with Gemini function calling to dynamically select diagnostic and remediation tools rather than following hardcoded if-else paths.
- **Strict In-Code Safety Policy**: Enforces read-only auto-approval, strict remediation allowlists, high-risk human approval gates, loop prevention, bounded iteration limits, and timeout protection directly in Python code.
- **Independent Recovery Verification**: Prohibits marking incidents as `RESOLVED` until independent multi-criteria checks verify nominal health, error rate under 5%, dependency recovery, and zero configuration drift.
- **Dual Runtimes (Live & Offline)**: Ships with live Gemini model integration and a deterministic `MockLLMClient` for 100% reproducible testing and offline evaluation without API keys.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Core Agent & LLM SDK**: Official Google Gen AI SDK (`google-genai` >= 2.0.0)
- **Data Validation & Schemas**: Pydantic 2.x (`pydantic` >= 2.0.0)
- **Environment Management**: `python-dotenv` >= 1.0.0
- **Testing Framework**: `pytest` >= 8.0.0
- **Simulated Environment**: In-memory deterministic microservice simulator (`ServiceSimulator`)

---

## Architecture & Data Flow

The agent operates as a state machine tracking explicit lifecycle states:
`DETECTED` ➔ `INVESTIGATING` ➔ `DIAGNOSED` ➔ `REMEDIATING` ➔ `VERIFYING` ➔ `RESOLVED` / `ESCALATED` / `FAILED`.

```
                  +-------------------------------------------------+
                  |          [1. Incident Detected]                 |
                  |  - Initial Telemetry & Severity Assessment      |
                  |  - Protective Escalation if Security Risk       |
                  +-----------------------+-------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                            [2. Autonomous Reasoning Loop]                         |
|                                                                                   |
|  +--------------------+        Prompt + State        +-------------------------+  |
|  |   Gemini Client    | <==========================> |   Incident Orchestrator |  |
|  | (Live / Mock Mode) |    Tool Selection / Decision |   - Lifecycle States    |  |
|  +--------------------+                              |   - In-Memory Record    |  |
|                                                      +------------+------------+  |
|                                                                   |               |
|                                                                   v               |
|                                                      +-------------------------+  |
|                                                      |  Safety Policy Engine   |  |
|                                                      |  - Read-Only Auto-Pass  |  |
|                                                      |  - Action Allowlist     |  |
|                                                      |  - Approval Gate        |  |
|                                                      |  - Loop Guard & Timeout |  |
|                                                      +------------+------------+  |
|                                                                   |               |
+-------------------------------------------------------------------|---------------+
                                                                    v
                                                       +-------------------------+
                                                       |     Tool Dispatcher     |
                                                       |  (Pydantic Validation)  |
                                                       +------------+------------+
                                                                    |
                                                                    v
                                                       +-------------------------+
                                                       |    Service Simulator    |
                                                       |  - Health & Logs        |
                                                       |  - Metrics & Config     |
                                                       |  - Dependencies         |
                                                       +-------------------------+
```

---

## Prerequisites

Before running this project, ensure you have:
- **Python**: Version 3.10, 3.11, or 3.12 installed
- **Package Manager**: `pip` (Python package installer)
- **Gemini API Key** *(Optional for live LLM mode)*: Available for free via [Google AI Studio](https://aistudio.google.com/app/apikey). Offline mock mode runs completely without an API key.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/autonomous-incident-responder
   ```

2. **Create and activate a virtual environment:**
   - **Windows (PowerShell):**
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\activate
     ```
   - **Linux / macOS:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables:**
   Copy the example environment template:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and insert your Gemini API key (if using live model mode).

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `GEMINI_API_KEY` | Conditional | *None* | Google AI Studio Gemini API key. Required only when passing `--use-gemini`. |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Gemini model identifier supporting function calling (e.g., `gemini-2.5-flash`, `gemini-2.5-pro`). |
| `MAX_ITERATIONS` | No | `10` | Maximum reasoning iterations allowed before forcing safe termination or escalation. |
| `MAX_TOOL_CALLS` | No | `15` | Maximum number of tool invocations allowed per incident lifecycle. |
| `OPERATION_TIMEOUT_SECONDS` | No | `35.0` | Execution timeout in seconds for API calls and tool handlers. |
| `LOG_LEVEL` | No | `info` | Logging verbosity (`debug`, `info`, `warn`, `error`). |

---

## How to Run

The agent entrypoint is `main.py`. It supports deterministic fault-injection scenarios and interactive or automated approval flags.

### 1. Offline Deterministic Mode (Default - No API Key Required)
Run reproducible simulated incident scenarios using the built-in deterministic reasoning engine:

```bash
# Scenario A: Invalid configuration drift (Rolls back configuration and verifies recovery)
python main.py --scenario config_drift --auto-approve

# Scenario B: Upstream dependency outage (Detects auth_service down, halts restart loops, escalates to humans)
python main.py --scenario dependency_down --auto-approve

# Scenario C: HTTP 500 error spike / thread pool starvation (Restarts service, clears leak, verifies healthy)
python main.py --scenario error_spike --auto-approve
```

### 2. Live Gemini Reasoning Mode (Requires `GEMINI_API_KEY`)
Run the autonomous agent with live Gemini function calling:

```bash
python main.py --scenario config_drift --use-gemini --auto-approve
```

### 3. Interactive Approval Mode
Omit `--auto-approve` to require interactive CLI confirmation whenever the agent requests a high-risk remediation action (e.g., `rollback_config`):

```bash
python main.py --scenario config_drift
```

---

## Example Input & Output

### Example Input Command
```bash
python main.py --scenario config_drift --auto-approve
```

### Example Execution Output
```text
======================================================================
[AGENT] Autonomous DevOps Incident Responder
======================================================================
[SETUP] Injecting invalid configuration fault into checkout-api...
[REASONING] Using deterministic MockLLMClient (offline, repeatable mode)

[INCIDENT DETECTED] INC-101: Checkout API Outage - Invalid Configuration Drift
Starting autonomous investigation loop...

======================================================================
Incident Response Completed: Status = [RESOLVED]
======================================================================
Total Iterations: 5
Total Tool Calls: 5
Severity Level: SEV-4
Response Priority: P4-LOW
Severity Reasons: All observed metrics and health checks are nominal (error rate < 5%, all dependencies healthy).
Root Cause: Configuration drift in parameters ['db_pool_size', 'request_timeout_ms']
Resolution Summary: Action 'rollback_config' successfully executed and verified healthy: Verification SUCCESS: Service is HEALTHY, error rate nominal, no config drift, all dependencies OK.
Final Service Status: HEALTHY [OK]
```

---

## How to Test

The repository includes a comprehensive test suite of 29 unit and scenario tests covering the simulator, tool dispatcher, safety policies, and severity classification.

### Run Automated Test Suite
```bash
pytest -v
```

### Test Scenarios Covered
1. **Invalid configuration diagnosed and corrected** (`test_1_invalid_configuration_diagnosed_and_corrected`)
2. **Unavailable dependency detected without repeatedly restarting** (`test_2_unavailable_dependency_detected_without_repeatedly_restarting`)
3. **Elevated error rate investigated and resolved** (`test_3_elevated_error_rate_investigated`)
4. **Failed remediation followed by further investigation** (`test_4_failed_remediation_followed_by_further_investigation`)
5. **Escalation when no safe fix is available** (`test_5_escalation_when_no_safe_fix_available`)
6. **Maximum iteration limits enforced** (`test_6_maximum_iteration_limit_enforced`)
7. **Invalid tool names and argument validation rejections** (`test_7_invalid_tool_calls_rejected`)
8. **Premature resolution blocked when health checks fail** (`test_8_resolution_prevented_when_health_checks_fail`)
9. **High-risk actions blocked without approval** (`test_9_high_risk_actions_blocked_without_approval`)
10. **Tool errors and execution timeouts handled safely** (`test_10_tool_errors_and_timeouts_handled_safely`)
11. **Severity classification tests (SEV-1 to SEV-4, uncertainty, security override, dynamic reassessment)** (`tests/test_severity.py`)

---

## Known Limitations

- **Simulated Environment Scope**: Remediations operate exclusively on the in-memory `ServiceSimulator`. The agent deliberately does not execute arbitrary operating system commands or connect to production clusters.
- **Free-Tier Gemini Rate Limits**: Free-tier Google AI Studio API keys are limited to 5 requests per minute. The client includes automatic retry backoff on HTTP 429 errors; however, high-frequency iteration loops may experience delay.
- **Stateless Execution**: Incident records and telemetry journals are stored in-memory per run; persistent database archival is out of scope for this version.

---

## Security & Privacy Considerations

- **Secrets Protection**: API credentials are loaded strictly through environment variables or local `.env` files via `python-dotenv`. Credentials are never logged, formatted into prompt history, or committed to Git.
- **Safety Sandboxing**: Tools do not invoke shell subprocesses or network socket connections outside the simulator.
- **Human Approval Controls**: High-risk actions (`rollback_config`) require explicit approval callback authorization unless specifically opted-out via `--auto-approve`.
- **Security Incident Protective Escalation**: Credible indicators of data corruption or security breach automatically trigger immediate protective escalation to human incident commanders, barring speculative automated remediations.

---

## Future Improvements

- [ ] Add support for streaming reasoning tokens in CLI.
- [ ] Connect with Prometheus/OpenTelemetry collectors for live cluster telemetry ingestion.
- [ ] Implement an interactive Streamlit operational dashboard.
- [ ] Support local open-weight models via Ollama or vLLM.

---

## License

*This project is contributed under the repository's open-source license.*
