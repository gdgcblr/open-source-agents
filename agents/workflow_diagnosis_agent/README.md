# AI-Powered Workflow Failure Diagnosis Agent

An AI-powered workflow failure diagnosis prototype built with Python and Google's Agent Development Kit (ADK). The project analyzes workflow execution results, identifies probable failure causes, and recommends practical debugging steps.

The current prototype uses sample workflow data stored in JSON. The long-term goal is to evolve it into an intelligent workflow troubleshooting agent that can inspect real CI/CD or data engineering workflow failures and help engineers investigate incidents faster.

## Project Overview

Data engineering workflows can fail for several reasons, including memory exhaustion, database connectivity problems, timeouts, and upstream dependency failures. Investigating these failures often requires manually reviewing logs and identifying the likely root cause.

This project explores how an AI agent can assist with that process by:

- Identifying successful and failed workflows.
- Interpreting error messages using a large language model.
- Suggesting probable root causes and debugging steps.
- Separating observed evidence from assumptions.
- Identifying additional logs and telemetry needed for a more confident diagnosis.

## Current Implementation

The project currently contains two diagnosis approaches.

### 1. Rule-Based Diagnosis

The existing `main.py` implements predefined rules to classify workflow failures.

It identifies common error patterns, including:

| Error pattern | Probable cause | Suggested action |
|---|---|---|
| Out of memory | Resource exhaustion | Inspect data volume, partitions, and memory settings |
| Connection error | Connectivity issue | Check database availability, network, and credentials |
| Timeout | Execution exceeded the allowed time | Inspect task duration, upstream delays, and timeout settings |
| Unrecognized error | Insufficient information | Review full logs and upstream task status |

The script also generates a daily summary of successful and failed workflows.

### 2. AI-Powered Diagnosis

The new `agent.py` uses Google's Agent Development Kit (ADK) and a Gemini model to interpret workflow data.

The agent exposes a Python tool, `get_workflow_data`, which reads workflow execution records from `workflows.json`.

The model analyzes the retrieved data and produces a structured explanation covering:

- Overall workflow status.
- Probable root causes.
- Supporting evidence.
- Assumptions and uncertainties.
- Additional diagnostic information required.
- Recommended debugging steps and potential fixes.

The AI-generated diagnoses are hypotheses based on the available input. They do not establish the actual root cause without supporting logs or telemetry.

## Architecture

```text
workflows.json
      |
      v
get_workflow_data()
      |
      v
Google ADK Agent
      |
      v
Gemini Model
      |
      v
AI-Generated Diagnosis
      |
      +--> Workflow status
      +--> Probable root cause
      +--> Evidence and assumptions
      +--> Recommended next steps
```

The current prototype reads local sample data. It does not yet retrieve live workflow runs or logs from external systems.

## Project Structure

```text
open-source-agents/
|
+-- agents/
|   |
|   +-- workflow_diagnosis_agent/
|       |
|       +-- agent.py
|       +-- main.py
|       +-- ai_diagnosis.py
|       +-- workflows.json
|       +-- README.md
|       +-- .env
|       +-- .env.example
|       +-- .gitignore
|       +-- __init__.py
|
+-- .venv/
|
+-- README.md
```

**Note:** `.venv/` and `.env` are local development files and should not be committed. `ai_diagnosis.py` was present in the working directory but had not yet been implemented. The agent currently uses `agent.py`.

## Technology Stack

- **Python 3.12:** Development environment.
- **Google ADK:** Agent definition, tool integration, and execution.
- **Gemini API:** Language-model-based workflow diagnosis.
- **JSON:** Input format for sample workflow execution records.
- **PowerShell:** Local development and execution on Windows.

## Prerequisites

Before running the prototype, install:

- Python 3.12.
- Git.
- A Google AI Studio API key.
- The Python dependencies required by Google ADK.

## Setup Instructions

### 1. Create and activate a virtual environment

From the project root:

```powershell
py -3.12 -m venv .venv
```

The virtual environment can be invoked directly in PowerShell without activation:

```powershell
.\.venv\Scripts\python.exe --version
```

### 2. Install Google ADK

```powershell
.\.venv\Scripts\python.exe -m pip install google-adk
```

### 3. Configure the API key

Create an API key through [Google AI Studio](https://aistudio.google.com/app/apikey).

Open the agent's environment file:

```powershell
notepad .\agents\workflow_diagnosis_agent\.env
```

Add the following configuration, replacing the placeholder with your own key:

```dotenv
GOOGLE_API_KEY=your_actual_api_key_here
```

Save the file.

**Security:** Never commit the API key to GitHub. Keep `.env` excluded from version control, and use `.env.example` only for placeholder configuration.

### 4. Run the AI agent

From the project root:

```powershell
.\.venv\Scripts\adk.exe run .\agents\workflow_diagnosis_agent
```

When the interactive session starts, enter:

```text
Analyze all workflow runs and explain the probable root causes of the failures.
```

The agent should read the JSON file and generate its diagnosis. Enter `exit` to leave the interactive session.

## Sample Input

The current `workflows.json` contains three example workflow runs:

```json
[
  {
    "name": "product_content_scoring",
    "status": "success"
  },
  {
    "name": "daily_pricing_pipeline",
    "status": "failed",
    "error_message": "Executor lost due to out of memory"
  },
  {
    "name": "customer_data_pipeline",
    "status": "failed",
    "error_message": "Database connection timeout"
  }
]
```

## Example Diagnosis

The AI agent successfully analyzed these sample records.

### 1. product_content_scoring

**Status:** Success

The workflow completed successfully according to the supplied status. No remediation is required based on the available input.

### 2. daily_pricing_pipeline

**Status:** Failed

**Observed evidence:** `Executor lost due to out of memory`

**Probable cause:** Resource exhaustion in the execution environment.

**Potential investigation steps:**

- Inspect executor and container memory usage.
- Review task and partition sizes.
- Check for skewed data or large shuffle operations.
- Review executor logs and cluster-manager diagnostics.
- Evaluate memory configuration if the evidence supports doing so.

### 3. customer_data_pipeline

**Status:** Failed

**Observed evidence:** `Database connection timeout`

**Probable cause:** A database connectivity, availability, or response-time issue.

**Potential investigation steps:**

- Check database availability and server health.
- Verify network connectivity and credentials.
- Review connection pool utilization and timeout settings.
- Inspect database and application logs around the failure timestamp.

These are possible explanations, not confirmed root causes. Additional execution logs and telemetry are required to verify them.

## What Has Been Completed

- [x] Inspected and retained the existing rule-based diagnosis implementation.
- [x] Prepared sample workflow execution data in JSON.
- [x] Set up Python 3.12 and a virtual environment.
- [x] Installed Google ADK.
- [x] Created an AI agent using `LlmAgent`.
- [x] Added a Python tool to load workflow records from JSON.
- [x] Configured API authentication through a local environment file.
- [x] Successfully ran the agent interactively.
- [x] Generated AI-based diagnoses for successful and failed workflows.

## Current Limitations

The current implementation is an early-stage prototype.

- Workflow data is loaded from a local JSON file.
- Live GitHub Actions or Airflow integration is not implemented.
- The agent does not retrieve production logs or metrics.
- Root-cause suggestions are not independently verified.
- Automated remediation, MCP integration, and A2A communication are not implemented.
- Automated tests, structured response validation, and robust API-error handling remain future work.

The agent does not execute fixes or verify workflow recovery.

## Roadmap

### Phase 1: Reliability

- Add unit tests for the existing rule-based diagnosis.
- Validate workflow input and AI response formats.
- Add API-error handling and a rule-based fallback.
- Improve diagnosis consistency and uncertainty reporting.

### Phase 2: Live GitHub Integration

- Connect to GitHub Actions.
- Retrieve real workflow runs and failure metadata.
- Fetch relevant logs for failed jobs.
- Provide evidence-grounded diagnoses instead of relying only on sample JSON.

### Phase 3: Better Log Analysis

- Extract relevant error messages and stack traces.
- Identify recurring failure patterns.
- Correlate errors with task, job, or execution metadata.
- Improve root-cause confidence without presenting guesses as facts.

### Phase 4: MCP Integration

- Expose workflow inspection and log retrieval as reusable tools through the Model Context Protocol (MCP).
- Separate external-system access from diagnosis logic.
- Apply appropriate permissions and input validation.

### Phase 5: Multi-Agent Collaboration

- Explore Agent-to-Agent (A2A) communication if multiple specialized agents provide clear value.
- Consider separate agents for log analysis, root-cause investigation, and remediation recommendations.
- Require explicit approval before any potentially disruptive remediation.

### Phase 6: Production Readiness

- Add automated tests and CI checks.
- Introduce structured logging and observability.
- Document permissions, API limits, and failure modes.
- Evaluate diagnostic quality against known failure scenarios.

## Contributing

Contributions and suggestions are welcome. Before opening a pull request:

1. Describe the problem being addressed.
2. Keep changes focused and testable.
3. Add tests for new diagnosis rules or agent behavior.
4. Never include API keys, credentials, or production logs containing sensitive data.
5. Document new integrations and their configuration requirements.

## License

Add the license applicable to this repository before distributing or reusing the project. Refer to the repository's existing licensing terms.

---

**Project status:** Working AI prototype using Google ADK and local JSON workflow data. Live workflow integration and production-hardening work are planned, not yet implemented.
