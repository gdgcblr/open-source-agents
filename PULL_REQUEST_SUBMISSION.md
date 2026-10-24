## Project Overview

- **Project Name:** BuildDoctor & BuildDoctor MCP
- **Category:** `agents/build-doctor` and `tools/build-doctor-mcp`
- **Frameworks & Technologies Used:** Google Agent Development Kit (ADK 1.12.0 for Java), Model Context Protocol (Python FastMCP SDK), Java 17+, Maven 3.9+, Python 3.10+, Gemini 2.5 Flash / Gemma 3 4B, DefusedXML, RxJava 3

### Description

### Why BuildDoctor? The Diagnostic Gatekeeper for Autonomous Development

Autonomous coding agents and IDE copilots are optimized to modify codebases and run tasks. However, when complex builds fail, CI breaks, or production APIs degrade, coding agents frequently suffer from **hallucinatory speculation**—modifying project code, guessing configuration values, or deleting dependencies without factual root cause evidence.

**BuildDoctor** solves this by acting as an **independent, evidence-based diagnostic gatekeeper and verification companion**:

1. **Evidence-Linked Root Cause Hypotheses:** Analyzes raw logs and manifests, extracting deterministic signal evidence and ranking hypotheses with transparent confidence levels, without hallucinating unsupported causes.
2. **Strict Verification Discipline:** Fixes remain strictly `pending` until developer-supplied before/after results are proven via `verify_resolution`. BuildDoctor refuses to declare a fix verified based purely on model confidence.
3. **Cross-Language ADK-to-MCP Architecture:** Seamlessly connects enterprise **Google ADK (Java 17+)** with the **Model Context Protocol (FastMCP Python 3.10+)** over standard `stdio`. Diagnostic capabilities are available to both ADK agents and any MCP-compatible client (Cursor, VS Code, Claude Desktop).
4. **Comprehensive Defense-in-Depth Boundary:** Completely read-only with zero shell execution, zero network requests, zero subprocess creation by tools, and zero destructive writes. Employs recursive symlink rejection, symlinked directory avoidance, multi-pattern credential redaction (Bearer tokens, API keys, private keys), aggregate output length caps, and prompt-injection neutralization (`[UNTRUSTED_TEXT]`).

#### Dual Execution Modes:
- **Zero-Cost Deterministic Mode:** Full failure classification, test report extraction, and before/after verification via Java CLI (`BuildDoctorCli` / `BuildDoctorApplication --diagnose`) and FastMCP with **0 API keys** and zero external token cost.
- **Model-Assisted ADK Mode:** Plugs into Google ADK with Gemini 2.5 Flash or local Gemma 3 4B to explain factual evidence while enforcing instructions that prevent LLMs from overriding deterministic scores or verification state.

---

## Contribution Checklist

Please verify the following requirements before submitting your PR:

- [x] **Directory & Naming:** The project is contained in its own folder under `agents/<project-slug>/` or `tools/<project-slug>/` using lowercase kebab-case.
- [x] **Documentation:** A complete `README.md` based on `template/README.md` is present in the project folder with all relevant sections completed.
- [x] **Reproducible Setup:** Setup and installation instructions were verified from scratch in a clean environment.
- [x] **Core Functionality Tested:** The agent or tool was executed and confirmed to work as described.
- [x] **Example Usage:** Realistic input and output examples are provided in the project documentation.
- [x] **Dependencies Declared:** All external dependencies are tracked in a project manifest (e.g., `requirements.txt`, `package.json`, `pyproject.toml`).
- [x] **Secrets & Security:** No API keys, credentials, tokens, local `.env` files, or personal data are included in this PR. A `.env.example` is provided if environment variables are required.
- [x] **Scope Limitation:** Changes are strictly confined to the project's own directory (plus an optional entry in `agents/README.md` or `tools/README.md` index). Unrelated files have not been modified.

---

## Testing & Verification Notes

### 1. Cross-Language ADK-to-MCP Integration Testing
- **Command:** `mvn test` in `agents/build-doctor/`
- **Result:** **15 tests passed, 0 failures, 0 skipped**
- **Verified Behaviors:**
  - Starts the Python FastMCP server as a child process via ADK `StdioServerParameters` over real `stdio`.
  - Dynamically discovers all 11 registered MCP tools.
  - Invokes `analyze_failure` and `verify_resolution` via ADK's `runAsync` and verifies structured JSON response deserialization.
  - Verifies child process lifecycle cleanup and resource disposal in a `finally` block.
  - Validates multi-pattern credential redaction (Bearer tokens, API keys, private keys) and prompt-injection sanitization in Java fallback.

### 2. Python FastMCP Protocol & Unit Test Suite
- **Command:** `uv run --with pytest pytest` in `tools/build-doctor-mcp/`
- **Result:** **34 tests passed in 2.23s**
- **Verified Behaviors:**
  - Real stdio client session initialization and tool listing.
  - Protocol invocation of `analyze_failure`, `inspect_project`, `verify_resolution`, and `format_incident_email`.
  - Tool-level security policy enforcement via `BUILD_DOCTOR_ALLOWED_TOOLS`.
  - XML report parsing with `defusedxml` and directory symlink containment.
  - Output bounding under `BUILD_DOCTOR_MAX_OUTPUT_CHARS`.
  - Prompt-injection neutralization replacing adversarial commands with `[UNTRUSTED_TEXT]`.
  - Generates Google Workspace / Gmail MCP dispatch envelope (`gmail.send_message`).

### 3. Public Evaluation Benchmark
- **Command:** `python evaluation/run.py` in `tools/build-doctor-mcp/`
- **Result:** **18/18 evaluation cases passed (100% accuracy)**
- **Coverage:** Tested across compilation errors, dependency resolution, API authentication, timeouts, rate limits, CI runner terminations, pytest assertion failures, schema validation, TLS/network errors, resource exhaustion, and concurrency deadlocks.

### 4. End-to-End Application CLI Verification
- **Connection Check:** `java -cp ... BuildDoctorApplication --check`
  - Output: `BuildDoctor MCP connection ready` with all 10 tools discovered.
- **Diagnostic Execution:** `java -cp ... BuildDoctorApplication --diagnose <log-file> [project-root]`
  - Output: Full structured JSON diagnostic report with hypotheses, evidence lines, remediation plan, and verification state.
