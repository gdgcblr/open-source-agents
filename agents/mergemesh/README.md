# MergeMesh — Cross-Repository Change-Set Compatibility Agent

> **Product Vision**: MergeMesh is designed to autonomously detect cross-repository compatibility risks and flag them to affected developers before incompatible changes reach production.

---

## Product Vision: An Autonomous Compatibility Agent

MergeMesh is designed as an autonomous compatibility agent that monitors software changes across independently maintained repositories, identifies downstream consumers affected by API or contract changes, verifies suspected incompatibilities through execution, and alerts responsible engineering teams before breaking changes ever reach a production deployment.

Today, cross-repository compatibility checking is predominantly a **manual, reactive, or fragmented activity**: developers must manually coordinate breaking changes over Slack, maintain bespoke end-to-end staging environments, or discover breakages only after a deployment failure. MergeMesh's long-term goal is to transform compatibility analysis into an **automated, continuous, and proactive background workflow** across multi-repository organizations.

---

## The Problem: Cross-Repository Blind Spots

In modern multi-repository and microservice architectures, services evolve independently:
- **The "Green CI" Trap**: Each repository maintains its own isolated continuous integration pipeline. A pull request in a provider repository (e.g., `orders-api`) can pass all of its isolated unit and integration tests. Simultaneously, a consumer repository (e.g., `checkout-client`) can pass all of its isolated tests because its test suite relies on **stale, hardcoded mock responses** created months earlier.
- **Contract Drift**: Routine changes—such as renaming a field (`customer_id` $\rightarrow$ `customerId`), removing a deprecated attribute, changing a value type (`integer` $\rightarrow$ `string`), or restructuring response objects—break consumer expectations silently.
- **The Impact of Undetected Drift**: When these independently passing versions are deployed together, the integration failure surfaces at runtime:
  - **Failed requests & runtime exceptions**: Consumers encounter unexpected `KeyError`, deserialization failures, or null reference errors.
  - **Interrupted business workflows**: Critical user journeys (such as checkout, billing, or event processing) can fail mid-transaction.
  - **Engineering firefighting & emergency rollbacks**: On-call engineers must perform triage across multiple service boundaries under pressure to diagnose which service introduced the mismatch.
  - **Delayed releases**: Deployment rollouts are halted while cross-team discussions clarify the intended schema.

MergeMesh addresses these blind spots by correlating candidate pull requests, diffing provider contracts, scanning consumer ASTs for affected lookups, and running controlled compatibility checks before changes merge.

---

## How Autonomous MergeMesh Is Intended to Work

MergeMesh envisions an end-to-end, seven-step autonomous compatibility lifecycle across independent codebases:

```text
[1. Detect]  --->  [2. Trace]  --->  [3. Verify]  --->  [4. Reason]  --->  [5. Notify]  --->  [6. Remediate]  --->  [7. Prevent]
 (Webhook/CI)       (AST Diff)        (Pytest)         (ADK+Gemma)        (PR/Email)         (Dual-Write)        (CI Gate)
```

1. **1. Detect (Planned Integration)**:
   A GitHub webhook listener or continuous integration workflow triggers MergeMesh automatically whenever a pull request or commit modifies an API contract, OpenAPI specification, or data model in a provider repository.
2. **2. Trace (Implemented in Prototype)**:
   MergeMesh inspects the provider contract diff across Git revisions (`base_ref` $\rightarrow$ `target_ref`) and scans registered consumer repositories using Python's `ast` module to identify potentially affected code down to the exact file paths, line numbers, and access patterns (`payload["key"]` vs `payload.get("key")`).
3. **3. Verify (Implemented in Prototype)**:
   MergeMesh runs controlled, bounded compatibility tests and strictly distinguishes between:
   - `INFERRED_RISK` (*Potential compatibility issue*): Static AST and contract analysis indicate an unhandled field modification, but no runtime test has been executed.
   - `REPRODUCED_FAILURE` (*Reproduced integration failure*): A dedicated cross-repository test executes against the proposed change set and reproduces the failure (e.g., `exit_code=1`, `KeyError`).
4. **4. Reason (Implemented in Prototype)**:
   Using Google Agent Development Kit (`google-adk`) with Google Gemma (hosted `gemma-4-26b-a4b-it` or local `gemma4:e4b`), MergeMesh reasons over the deterministic ground truth to explain what changed, why isolated CI checks passed, the operational severity, and architectural migration options. (When the model is unavailable, an honest deterministic fallback rule engine provides the structured analysis).
5. **5. Notify (Planned Integration)**:
   Rather than broadcast generic alerts, MergeMesh autonomously dispatches targeted notifications to affected repository owners and PR authors via GitHub PR comments, email digests, or CI check annotations, detailing the specific line of code affected, the schema diff, and the reproduced error.
6. **6. Remediate and Re-verify (Implemented in Prototype / Automated PRs Planned)**:
   MergeMesh guides developers on backward-compatible fixes—such as provider dual-writing during deprecation windows or consumer defensive dual-reading—and re-executes tests to verify that the remediation passes before merging.
7. **7. Prevent Release (Planned Integration)**:
   An optional CI status check policy gates merging when verified breaking failures (`BREAKING_FAILURE_REPRODUCED`) or high-severity unacknowledged risks are present, preventing incompatible changes from reaching production environments.

> [!NOTE]
> **Operational Status**: The current prototype executes Steps 2, 3, 4, and 6 on local Git repositories and bundled PR fixtures through a Streamlit UI and Python API. Steps 1 (GitHub webhooks), 5 (automated PR/email alerts), and 7 (CI policy merge gating) are planned roadmap integrations and are not yet automated background services.

---

## Why It Matters

Moving compatibility analysis from post-merge debugging to an autonomous pre-merge agent delivers substantial practical benefits:
- **Earlier Lifecycle Detection**: Detects breaking contract incompatibilities at pull-request time before candidate code merges into trunk branches or deploys to staging.
- **Eliminates Cross-Repo Blind Spots**: Surfaces mismatches that isolated unit tests miss due to stale, hardcoded consumer mocks.
- **Actionable Evidence Over Generic Warnings**: Delivers exact source locations (`file.py:line`), AST access types, and pytest failure traces directly to responsible developers rather than vague change notifications.
- **Reduces Production Incident Risks**: Mitigates the risk of unexpected runtime `KeyError` exceptions, transaction drop-offs, and emergency rollbacks caused by uncoordinated field deprecations.
- **Facilitates Safer Migrations**: Encourages disciplined backward-compatible rollout strategies (such as provider dual-writing and consumer dual-reading) with verified test evidence.

---

## Current Capabilities vs. Roadmap

The following table accurately reflects the current working implementation versus future roadmap integrations:

| Capability Area | Current Prototype | Planned Autonomous Roadmap | Implementation Status |
| :--- | :--- | :--- | :--- |
| **Trigger Mechanism** | Manual invocation via Streamlit UI (`app.py`) or Python API (`run_custom_repo_analysis`) | Automated GitHub App webhook triggers on `pull_request` and `push` events | **Planned** |
| **Provider Contract Extraction** | Deterministic `.json` (REST payloads / schemas) and `.py` AST (dict returns / typed models) across Git revisions (`main`, branches, commits, `WORKTREE`) | Automated OpenAPI / Protobuf / gRPC schema parsers and registry sync | **Implemented** (JSON & Python AST) |
| **Consumer Usage Analysis** | Python AST static scanner for `payload["key"]`, nested subscripts, and `payload.get("key")` with file/line evidence | Multi-language AST scanners (TypeScript, Go, Java) across consumer codebases | **Implemented** (Python AST) |
| **Consumer Discovery** | User specifies local consumer path or selects bundled multi-repo test scenarios | Centralized consumer repository registry with CODEOWNERS mapping | **Planned** |
| **Compatibility Verification** | Opt-in bounded `pytest` subprocess execution (`INFERRED_RISK` vs `REPRODUCED_FAILURE`) | Ephemeral isolated container runner in CI with sandboxed execution | **Implemented** (Local subprocess) |
| **AI Reasoning & Remediation** | Google ADK with hosted Gemma 4 (`gemma-4-26b-a4b-it`) or local Gemma (`gemma4:e4b`) + deterministic fallback | Autonomous agent dialogue: negotiates contract migration between author and consumers | **Implemented** (ADK + Gemma 4) |
| **Developer Notification** | Interactive 5-tab Streamlit dashboard with JSON and Markdown export | Automated sticky PR comments, email notifications, and GitHub Check Run annotations | **Planned** |
| **CI Merge Policy Enforcement** | Returns structured `AnalysisReport.overall_status` for headless scripting | Native GitHub Status Check blocking merge on `BREAKING_FAILURE_REPRODUCED` | **Planned** |
| **Automated Remediation PRs** | Generates verified Python remediation code snippets and re-verifies post-fix tests | Autonomously opens consumer migration pull requests with human review | **Planned** |

---

## Key Features (Current Prototype)

- **Reusable Local Git Repository Analyzer**: Point MergeMesh at any local provider Git repository and consumer Git repository, specify base and proposed Git revisions (`HEAD~1`, `main`, branch names, commit SHAs, or `WORKTREE`), and analyze real repository changes (`analysis/git_inspector.py`, `services/analyze_service.py`).
- **Dual Contract Extraction (`.json` & `.py` AST)**: Extracts before/after provider response shapes from JSON contract/schema files (`.json`) or directly from Python provider source files (`.py` functions returning dictionary literals or annotated `BaseModel` / `TypedDict` / `@dataclass` classes) via `analysis/contract_extractor.py`.
- **Python AST Consumer Usage Scanner**: Scans consumer Python files (`analysis/consumer_usage.py`) using Python's `ast` module to locate dictionary subscript (`payload["field"]`), nested subscript (`data["customer"]["id"]`), and `.get("field")` accesses with exact file paths, line numbers, and code snippets.
- **Strict Static vs. Reproduced Failure Distinction**:
  - `INFERRED_RISK` (*"Potential compatibility issue"*): Reported when static contract diffing and consumer AST analysis detect a breaking mismatch but no runtime integration test has been executed.
  - `REPRODUCED_FAILURE` (*"Reproduced integration failure"*): Reported only when an explicitly approved integration test executes and fails (`exit_code=1`).
- **Opt-In Safe Test Execution**: Bundled fixture tests run from an internal allow-list (`execution/fixture_registry.py`), while custom repository `pytest` files require explicit opt-in approval (`user_approved_test_execution=True`) before running in a bounded local subprocess (`execution/runner.py`).
- **Google ADK & Gemma Reasoning (Hosted & Local)**: Uses Google Agent Development Kit (`google-adk`) with `LiteLlm` supporting hosted Google Gemma 4 (`gemma-4-26b-a4b-it` via the Gemini Developer API) or local Gemma (`gemma4:e4b` via Ollama), with automatic fallback to the built-in **Deterministic Local Rule Engine** when models are offline.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+ (tested on Python 3.10 and Python 3.13)
- **Agent Framework / Core Library**: Google Agent Development Kit (`google-adk`), `litellm`, `pydantic`
- **Models**: Local `gemma4:e4b` (default), `gemma4:e2b` (lower-resource alternative), or `gemma3:4b` via Ollama (`ollama_chat/<OLLAMA_MODEL>`), plus built-in **Deterministic Local Rule Engine** (requires no LLM runtime)
- **UI & Visualization**: Streamlit (`streamlit`), Graphviz DOT dependency graphs
- **Test & Analysis Stack**: `pytest`, `fastapi`, `httpx`, Git CLI (`git rev-parse`, `git show`, `git diff`, `git ls-tree`), Python standard library (`ast`, `json`, `subprocess`, `hashlib`)

---

## Architecture & Data Flow

```text
[Streamlit UI (app.py / ui/)]  OR  [Python API (run_custom_repo_analysis / run_scenario_analysis)]
        |
        v
[Analysis Coordinator (services/analyze_service.py)]
        |
        +---> [1. Input Loader]
        |         - Custom Git Repos: analysis/git_inspector.py (git rev-parse, git show, git diff)
        |         - Bundled Scenarios: services/scenario_loader.py (fixtures/scenarios/<id>/)
        |
        +---> [2. Deterministic Contract Extractor (analysis/contract_extractor.py)]
        |         Extracts & diffs .json or .py contracts across base_ref and target_ref
        |
        +---> [3. Python AST Consumer Scanner (analysis/consumer_usage.py)]
        |         Extracts payload["field"] & payload.get("field") with file paths & line numbers
        |
        +---> [4. Controlled Pytest Runner (execution/runner.py)]
        |         Runs allow-listed fixture tests OR explicitly approved user repo pytest files
        |
        +---> [5. Compatibility Evaluator (analysis/compatibility.py)]
        |         Produces Findings (INFERRED_RISK vs REPRODUCED_FAILURE) & EvidenceItems
        |
        +---> [6. Local ADK Workflow (agents/workflow.py)]
                  Invokes local Ollama Gemma via ADK LiteLlm (if running on localhost)
                  OR synthesizes Deterministic Explanation (if Ollama is offline / deterministic mode)
        |
        v
[Typed AnalysisReport (domain/models.py)] ---> [Dashboard Tabs + JSON/Markdown Export]
```

### Supported Languages, Contract Formats & Analysis Rules
- **Provider Contract Formats**:
  - **JSON (`.json`)**: Sample REST JSON object payloads or JSON Schema objects containing `properties` and optional `required` arrays.
  - **Python (`.py`)**: Provider functions returning dictionary literals (`return {"customer_id": cid, "status": "active"}`) or classes (`BaseModel`, `TypedDict`, `@dataclass`) with type-annotated attributes.
- **Consumer Source Language**:
  - **Python (`.py`)**: Static string dictionary subscripts (`payload["field"]`, `data["nested"]["field"]`) and `.get("field")` calls parsed via Python `ast`.
- **Compatibility Rules**:
  1. `FIELD_REMOVED_BUT_CONSUMED` (`HIGH`): A field present in `base_ref` is removed in `target_ref` while the consumer AST still accesses it.
  2. `MISSING_REQUIRED_FIELD` (`HIGH`): A declared required field is missing in `target_ref`.
  3. `FIELD_TYPE_CHANGED` (`HIGH` / `MEDIUM`): A field's value type changes incompatibly (e.g., `integer` $\rightarrow$ `string`) between `base_ref` and `target_ref`.
  4. **Candidate Rename Detection**: Heuristic matching of removed and added fields at the same nesting level (`customer_id` $\leftrightarrow$ `customerId`).

---

## Prerequisites & Ollama Setup

1. **Python**: Python `3.10` or higher (`python --version`; tested on Python 3.10 and Python 3.13).
2. **Git**: `git` CLI available in `PATH` (`git --version`) for inspecting local Git repositories and revisions.
3. **Package Manager**: `pip` (`python -m pip --version`).
4. **API Keys / Cloud Credits**: **None required.** MergeMesh runs 100% locally without any API keys or cloud credentials.
5. **Local Gemma Reasoning via Ollama (Primary AI Mode)**:
   - Install [Ollama](https://ollama.com/download) (`winget install Ollama.Ollama` on Windows, `brew install ollama` on macOS, or the official install script on Linux).
   - Start the local Ollama daemon if it is not already running:
     ```bash
     ollama serve
     ```
   - Pull the validated primary reasoning model **`gemma4:e4b`** (or **`gemma4:e2b`** for lower VRAM/RAM, or **`gemma3:4b`**):
     ```bash
     ollama pull gemma4:e4b
     # Lower-resource alternative:
     # ollama pull gemma4:e2b
     ```
   - Verify Ollama is serving the model locally:
     ```bash
     ollama list
     ```
   - *First-Run Honesty Note*: If Ollama is not installed or not running on `http://localhost:11434`, MergeMesh **never** disguises fallback output as live Gemma output. Both the CLI and Streamlit UI prominently display `[DETERMINISTIC FALLBACK MODE (status=FALLBACK) — NOT LIVE GEMMA OUTPUT]` along with the exact recovery command.

---

## Installation & Setup (Clean Checkout)

1. **Navigate to the project directory:**
   ```bash
   cd agents/mergemesh
   ```

2. **Create and activate an isolated virtual environment:**
   - **Windows (PowerShell):**
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     python -m pip install --upgrade pip
     python -m pip install -r requirements.txt
     ```
   - **Linux / macOS:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     pip install --upgrade pip
     pip install -r requirements.txt
     ```

3. **Configure Environment Variables (Optional):**
   MergeMesh runs with safe local defaults out of the box (`MERGEMESH_AI_MODE=local`, `OLLAMA_MODEL=gemma4:e4b`). To customize settings, copy `.env.example` to `.env`:
   ```bash
   # Windows PowerShell:
   Copy-Item .env.example .env

   # Linux / macOS:
   cp .env.example .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `MERGEMESH_AI_MODE` | No | `local` | `local` (Primary Gemma reasoning via Ollama + Google ADK with explicit fallback) or `deterministic` (Pure Python engine, zero LLM calls) |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Local loopback URL for Ollama (`localhost` / `127.0.0.1` / `::1` enforced) |
| `OLLAMA_MODEL` | No | `gemma4:e4b` | Validated local Ollama model tag (`gemma4:e4b` primary, `gemma4:e2b` lightweight, or `gemma3:4b`) |
| `ALLOW_LOCAL_FALLBACK` | No | `true` | When `true`, preserves deterministic findings and returns `status="FALLBACK"` if Ollama is offline; when `false`, returns `status="UNAVAILABLE"` |
| `TEST_RUNNER_TIMEOUT_SECONDS` | No | `15` | Maximum timeout in seconds for each `pytest` subprocess |
| `AI_REQUEST_TIMEOUT_SECONDS` | No | `25` | Maximum timeout in seconds for local Ollama inference requests |
| `AI_MAX_OUTPUT_TOKENS` | No | `1200` | Maximum completion tokens (`num_predict`) requested from Ollama |

---

## How to Run

### 1. Launch the Interactive Streamlit Dashboard
```bash
python -m streamlit run app.py
```

In the sidebar under **Analysis Input Source**, choose between:
- **Local Git Repositories (Custom Paths & Refs)**:
  1. Enter your local **Provider Repo Path** (e.g., `/path/to/orders-provider`), **Base Git Ref** (e.g., `main` or `HEAD~1`), and **Proposed Git Ref** (e.g., `HEAD`, a feature branch name, or `WORKTREE`).
  2. Optionally enter the relative **Contract File Path** (`.json` or `.py`), or leave it blank to auto-discover.
  3. Enter your local **Consumer Repo Path** (e.g., `/path/to/checkout-consumer`) and **Consumer Target Ref** (e.g., `main` or `HEAD`).
  4. *(Optional)* Open **3. Optional Pytest Execution (Explicit Approval)**, check **"I approve executing the configured pytest files locally"**, and enter relative `.py` test paths (e.g., `tests/test_cross_repo_integration.py`).
  5. Click **Analyze Change Set**.
- **Bundled Example Scenarios**:
  - Select **Scenario A — Breaking Field Rename (`customer_id` $\rightarrow$ `customerId`)** or **Scenario B — Compatible Optional Field Addition (`display_name`)** for an immediate fixture demonstration.

### 2. Analyze Any Local Git Repositories via Python API
```python
from services.analyze_service import CustomRepoAnalysisRequest, run_custom_repo_analysis

report = run_custom_repo_analysis(
    CustomRepoAnalysisRequest(
        provider_repo_path="/path/to/provider-repo",
        consumer_repo_path="/path/to/consumer-repo",
        provider_base_ref="HEAD~1",
        provider_target_ref="HEAD",
        consumer_target_ref="HEAD",
        user_approved_test_execution=False,  # Static analysis only by default
    )
)
print("Overall Verdict:", report.overall_status)
print("AI Mode Status:", report.ai_explanation.status, "| Model:", report.ai_explanation.model)
```

---

## Example Input & Output

### Example 1: Analyzing Custom Local Git Repositories (`billing-service` & `invoice-worker`)
- **Input**:
  - `provider_repo_path`: `/tmp/billing-service` (`HEAD~1` $\rightarrow$ `HEAD`, where `schemas/v1/account.json` renames `"account_uuid"` $\rightarrow$ `"accountUuid"`)
  - `consumer_repo_path`: `/tmp/invoice-worker` (`HEAD`, where `jobs/invoice_sync.py` reads `payload["account_uuid"]`)
- **Output (Static Analysis, `user_approved_test_execution=False`)**:
  ```text
  Input Mode: local_git_repos
  Overall Verdict: POTENTIAL_COMPATIBILITY_ISSUE
  Finding: [HIGH] missing_account_uuid (FIELD_REMOVED_BUT_CONSUMED | verification_state=INFERRED_RISK)
  Summary: Potential compatibility issue: billing-service removed 'account_uuid' (renamed to 'accountUuid') while invoice-worker still reads 'account_uuid'.
  Evidence:
    - [provider_contract_before] billing-service@HEAD~1:schemas/v1/account.json
    - [provider_contract_after]  billing-service@HEAD:schemas/v1/account.json
    - [consumer_access]          jobs/invoice_sync.py:2 (return payload["account_uuid"])
  ```
- **Output (With Approved Integration Test, `user_approved_test_execution=True`)**:
  ```text
  Overall Verdict: BREAKING_FAILURE_REPRODUCED
  Finding: [HIGH] missing_account_uuid (verification_state=REPRODUCED_FAILURE)
  Combined Test: tests/test_integration.py -> FAIL (exit_code=1, KeyError: 'account_uuid')
  ```

### Example 2: Reproducing Bundled Scenario A (`customer_id_rename`) & Scenario B (`safe_optional_field`)
- **Scenario A (`customer_id_rename`)**:
  - Isolated tests `test_provider_unit.py` (`PASS`) and `test_consumer_unit.py` (`PASS` using stale mock) succeed, while `test_combined_contract.py` fails with `KeyError: 'customer_id'` (`BREAKING_FAILURE_REPRODUCED`). Clicking **Verify Suggested Fix** runs `test_post_fix_contract.py` and passes (`REMEDIATED_PASS`).
- **Scenario B (`safe_optional_field`)**:
  - Provider adds optional `"display_name"` while preserving `"customer_id"`. All isolated and combined checks pass with `0` findings (`COMPATIBLE_PASS`).

---

## How to Test & Verification Scope

Run the automated verification suite (unit tests, bundled scenario integration tests, independent temporary Git repository tests, timeout/invalid-JSON fallback tests, headless Streamlit `AppTest` UI tests, and hosted Gemma API smoke test) from `agents/mergemesh`:

```bash
python -m pytest -v
```

### What Has and Has Not Been Tested with a Live Model
- **Verified End-to-End in Automated Tests**:
  - Deterministic `.json` and `.py` AST contract extraction, consumer Python AST field usage scanning, and Git revision inspection across independent repositories.
  - Controlled `pytest` execution (`PASS` vs `FAIL`, `INFERRED_RISK` vs `REPRODUCED_FAILURE`).
  - Google ADK `InMemoryRunner` $\rightarrow$ `LiteLlm` $\rightarrow$ `HostedGemmaLiteLLMClient` / `OllamaLiteLLMClient` request formatting (`role="system"` normalization, `response_format={"type": "json_object"}`, evidence prompt construction) and Pydantic schema validation (`AIExplanationSchema`).
  - Timeout (`TimeoutError`), offline Ollama server, missing model tag, and malformed JSON fallback behavior (`status="FALLBACK"` / `status="UNAVAILABLE"`).
  - Live hosted Gemma 4 inference (`gemma-4-26b-a4b-it`) via the Google Gemini Developer API verified via live smoke test (`test_hosted_gemma_live_api_smoke_test`).
- **Requires Local Ollama Runtime Installation (For Local AI Mode)**:
  - Live token generation from `gemma4:e4b` / `gemma4:e2b` / `gemma3:4b` over `http://localhost:11434` requires installing the Ollama daemon and running `ollama pull gemma4:e4b` on the host machine. When Ollama is not installed on the test runner, MergeMesh explicitly reports `status="FALLBACK"` and never claims live model execution occurred.
- **Hosted Mode**:
  - Requires `GEMINI_API_KEY` in `.env` or environment to run live inference against `gemma-4-26b-a4b-it`. If the key is not set, MergeMesh safely skips external network calls and displays an explicit `UNAVAILABLE` or `FALLBACK` status.

---

## Troubleshooting Common Failures

| Symptom / Status | Cause | Resolution |
| :--- | :--- | :--- |
| **`Ollama service offline and CLI not found`** (`status=FALLBACK`) | Ollama is not installed or `ollama serve` is not running on `http://localhost:11434` | Install Ollama from [ollama.com](https://ollama.com), run `ollama serve`, and pull `gemma4:e4b`. |
| **`Ollama running, but model 'gemma4:e4b' is not pulled`** (`status=FALLBACK`) | Ollama server is reachable on port `11434`, but the configured `OLLAMA_MODEL` tag has not been downloaded yet | Run `ollama pull gemma4:e4b` (or set `OLLAMA_MODEL=gemma4:e2b` / `gemma3:4b` in `.env` to match an already installed tag from `ollama list`). |
| **`Local AI invocation or schema validation failed: TimeoutError`** | Local model cold-start or CPU inference exceeded `AI_REQUEST_TIMEOUT_SECONDS` (`25s` default) | Increase `AI_REQUEST_TIMEOUT_SECONDS=60` in `.env` or switch to the lighter `OLLAMA_MODEL=gemma4:e2b`. |
| **`ValidationError` / Malformed Model Output** (`status=FALLBACK`) | Local model returned truncated JSON (e.g., token limit reached) or omitted required schema keys | Increase `AI_MAX_OUTPUT_TOKENS=1600` in `.env`. MergeMesh automatically catches malformed output and falls back to the deterministic engine without crashing. |
| **`Blocked non-local OLLAMA_BASE_URL`** | `OLLAMA_BASE_URL` points to a non-loopback remote host | Set `OLLAMA_BASE_URL=http://localhost:11434` (MergeMesh enforces loopback-only URLs). |

---

## Current Status and Roadmap

### 1. Implemented and Verified Today
- **Deterministic Cross-Repo Analyzer**: Extracts and diffs `.json` and `.py` AST provider contracts across arbitrary local Git revisions (`main`, branches, tags, commit SHAs, `WORKTREE`) and scans consumer Python AST dictionary accesses (`payload["key"]`, `.get("key")`).
- **Multi-Repository Integration Verification (`tests/integration/test_custom_repo_workflow.py`)**: Automated integration tests create genuinely independent temporary Git repositories (`orders_service` and `checkout_service`) with separate Git histories to verify breaking field renames (`customer_id` $\rightarrow$ `customerId`), harmless additive changes (`display_name`), and offline deterministic fallback.
- **Google ADK + Gemma Reasoning Pipeline**: Structured prompt builder (`agents/prompts.py`), ADK `InMemoryRunner` + `LiteLlm` client (`agents/factory.py`), `<think>`-aware JSON parser, schema validator (`agents/schemas.py`), and grounding guardrails (`agents/workflow.py`).
- **Explicit Operating Modes & Streamlit UI**: 5-tab Streamlit dashboard (`app.py`) and Markdown/JSON exporter that strictly separate deterministic findings from AI interpretation and visibly distinguish `Gemma Mode Active (status=SUCCESS)` from `Deterministic Fallback Mode (status=FALLBACK)`.

### 2. Prototype / Manual Workflow Today
- **Manual Launch & Local Repository Selection**: Today, a developer runs `python -m streamlit run app.py` (or invokes `run_custom_repo_analysis()` from Python) locally and selects the local filesystem paths and Git revisions for the provider and consumer repositories.
- **No Automated GitHub Webhook or PR Bot Yet**: MergeMesh does not currently include a deployed GitHub App, webhook listener, or live `.github/workflows/` PR comment bot.

### 3. Planned: Path to Automated GitHub Actions PR Checks
To evolve MergeMesh from a local pre-merge analyzer into an automated CI gate across multi-repo microservices:
- **Triggering Repository (`pull_request` workflow)**:
  - A GitHub Actions workflow in either the **provider repository** (on PRs modifying `contracts/**` or API route modules) or the **consumer repository** triggers on `pull_request` events.
- **Partner Repository Discovery & Checkout**:
  - A declarative `.mergemesh.yaml` manifest in the repository root specifies the partner repository slug (e.g., `org/checkout-consumer`), default target branch (`main`), contract path, and optional integration test command.
  - The workflow uses `actions/checkout` twice: once for the PR head revision (`HEAD`) and once to clone the partner repository into a sibling workspace directory using a fine-grained, read-only repository deploy key or scoped `GITHUB_TOKEN`.
- **Execution, Timeouts & Graceful Fallback in CI**:
  - The CI job runs `run_custom_repo_analysis()` in headless CLI mode and writes `report_<id>.json` and `report_<id>.md`.
  - If an internal Ollama runner or self-hosted GPU runner is configured, Gemma generates the contextual PR summary within `AI_REQUEST_TIMEOUT_SECONDS`; if no model runner is available in CI, `MERGEMESH_AI_MODE=deterministic` (or automatic `FALLBACK`) guarantees the check still completes deterministically with zero external API keys.
- **Publishing Evidence-Backed PR Results**:
  - A final workflow step posts or updates a single sticky PR comment from the generated Markdown report (`export_report_to_markdown(report)`) and sets the GitHub Check Run exit code (`1` on `BREAKING_FAILURE_REPRODUCED` or high-severity `POTENTIAL_COMPATIBILITY_ISSUE`, `0` on `COMPATIBLE_PASS`).
- **Credential-Free CI Testing**:
  - All automation logic is testable offline using temporary local Git repositories (`tests/integration/test_custom_repo_workflow.py`) without requiring live GitHub tokens or cloud model credentials.

---

## Known Limitations

- **Supported Contract & Language Scope**: Provider contract extraction supports JSON files (`.json`) and Python files (`.py`) containing functions that return dictionary literals or annotated model classes (`BaseModel`, `TypedDict`, `@dataclass`). Consumer usage scanning supports static string dictionary subscripts (`payload["key"]`) and `.get("key")` calls in Python `.py` files. Dynamic key lookup (`payload[var]`), complex runtime serialization, or non-Python languages are not parsed.
- **Subprocess Execution Boundary**: Opt-in test execution runs `python -m pytest` as a local OS subprocess (`shell=False`, sanitized environment variables, bounded timeout). It is **not** a container, VM, or kernel sandbox; only approve test execution on local repositories you trust.
- **Local Ollama Availability**: If Ollama is not running on `localhost:11434` or the configured `OLLAMA_MODEL` (`gemma4:e4b` by default) is not pulled, MergeMesh does not claim local LLM generation occurred; it labels the explanation status as `FALLBACK` (or `SKIPPED` in `deterministic` mode) and uses the deterministic rule engine.

---

## Security & Privacy Considerations

- **Zero Secrets & Zero External Network Calls**: MergeMesh requires no API keys and never transmits repository code, diffs, contracts, test outputs, or prompts to external AI services. `config/settings.py` enforces loopback-only URLs (`localhost` / `127.0.0.1` / `::1`) for local Ollama checks.
- **Explicit Opt-In for User Repo Tests**: In Custom Git Repository mode, `user_approved_test_execution` defaults to `False`. MergeMesh never automatically executes code from analyzed repositories.
- **Command & Path Validation**: All Git and `pytest` commands run with `shell=False`, reject leading `-` flag injection on revision/path inputs, and reject `..` path traversal outside the repository root.

---

## License

*This project is contributed under the repository's open-source [MIT License](../../LICENSE).*
