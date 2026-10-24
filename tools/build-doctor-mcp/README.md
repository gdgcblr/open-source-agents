# BuildDoctor MCP Server

> A read-only Model Context Protocol server that gives any MCP-compatible client evidence-based diagnosis for build, test, runtime, and API failures.

## Overview

### Problem Statement & Intended Users

Failure diagnosis is slow when logs are large, symptoms are misleading, and project context is scattered across manifests. This server exposes safe diagnostic tools that work with any language, build system, framework, or API because they accept evidence rather than assuming one ecosystem.

Intended users include developers, open-source contributors, students, support engineers, and AI assistants connected through MCP.

### Why BuildDoctor Exists Alongside Coding Agents

Cursor, IDE copilots, and autonomous coding agents are optimized to change a codebase and execute a development task. BuildDoctor has a different role: it is an independent, evidence-first failure investigator that produces a reviewable diagnosis before anyone changes code.

Its differentiators are:

- **Evidence over confident guessing:** every hypothesis is linked to observed log or manifest evidence.
- **Language and provider neutrality:** the input contract accepts build, test, runtime, and API output from any ecosystem.
- **Verification discipline:** a suggested fix is never reported as successful until a new result is supplied.
- **Safety boundary:** the MCP server reads bounded evidence and never edits files, executes commands, or installs dependencies.
- **Portable integration:** any MCP-compatible client can use the same tools and structured response.

### Target User Workflow

1. The developer runs the normal build, test, or API check and saves the relevant output.
2. The developer connects BuildDoctor to an MCP client and selects the project workspace.
3. The client calls `summarize_diagnosis` with the failure output and project path.
4. BuildDoctor returns evidence, ranked hypotheses, missing information, and a safe remediation plan.
5. The developer reviews and applies a change using their normal coding agent or editor.
6. The developer supplies the original and new results to `verify_resolution`; only deterministic before/after evidence can mark the issue verified.
7. The developer may use `compare_diagnoses` for trend reporting; only structured fields are compared, not stored raw logs.

BuildDoctor is therefore a diagnostic gate and verification companion, not another autonomous code editor.

### Key Features

- `analyze_failure`: classify common compilation, dependency, test, runtime, and API failure signals.
- `inspect_project`: read bounded content from recognized project manifests without executing code.
- `inspect_test_reports`: parse bounded JUnit, Surefire, and pytest-style XML reports into factual test evidence.
- `summarize_diagnosis`: combine failure evidence and project metadata in one JSON response.
- `analyze_alert`: normalize provider alerts from New Relic, CubeAPM, Prometheus, OpenTelemetry, or custom webhooks.
- `inspect_ci_annotations`: extract GitHub/GitLab/Azure-style error and warning annotations from CI output.
- `inspect_api_error`: normalize common JSON API error envelopes with status, message, request ID, and retry guidance.
- `compare_diagnoses`: compare structured results across runs without retaining or re-reading raw logs.
- `verify_alert_signature`: verify an HMAC-signed gateway payload before alert analysis.
- `verify_resolution`: compare supplied before/after output and report `verified` only when deterministic success evidence is present.
- Deterministic categories for compilation, dependencies, tests, runtime/API, configuration, permissions, network/TLS, resources, data/schema, CI/container, and concurrency/state failures.
- Versioned diagnostic responses with hypotheses, confidence, evidence gaps, remediation, and verification state.
- Deterministic signal IDs and scores make classification inspectable and reproducible for the same input.
- Standard MCP stdio transport for desktop and editor clients.
- Real stdio protocol coverage verifies server startup, tool discovery, and tool invocation.
- Redaction, input limits, optional workspace allowlisting, and no automatic remediation.

## Technical Stack

- **Language & Runtime:** Python 3.10+
- **Protocol:** Model Context Protocol (MCP)
- **SDK:** Official Python MCP SDK
- **Transport:** stdio
- **Dependencies:** `mcp>=1.6,<2`, `defusedxml>=0.7.1,<1`

## Architecture & Data Flow

```text
[MCP client] <stdio> [BuildDoctor MCP server]
                              |
  +-----+----------+----------------------+
  |                |                      |
[Failure analyzer] [Manifest/report reader] [Alert normalizer]
  |                |                      |
  +----------------+--------> [Structured JSON evidence]
```

The server never runs project commands. The client supplies a log and, optionally, a project directory for bounded read-only inspection.

## Observability Integration

BuildDoctor does not poll or mutate monitoring systems. Use a provider webhook or a small secure gateway:

```text
[New Relic/CubeAPM/Prometheus/Otel alert]
      |
       [authenticated webhook gateway]
      |
       [MCP client or coding agent]
      |
    analyze_alert(provider, payload)
      |
       [deterministic evidence + next checks]
      |
       summarize_diagnosis(log, project_path)
```

The provider adapter should map vendor fields into the contract shown in [`examples/observability-alert.json`](examples/observability-alert.json). The standard fields are `event_type`, `service`, `environment`, `metric`, `value`, `threshold`, `unit`, `condition`, `timestamp`, and `correlation_id`. Vendor-specific fields may be retained in the gateway, but only sanitized evidence should be sent to BuildDoctor. Configure `BUILD_DOCTOR_WEBHOOK_SECRET` and call `verify_alert_signature` before `analyze_alert`; signature verification fails closed when no secret is configured.

See [`examples/observability-gateway/README.md`](examples/observability-gateway/README.md) for the provider-adapter boundary and signature responsibilities.

Supported event categories include latency, error rate, availability, saturation, deployment, security, certificate expiry, and queue lag. A threshold breach identifies an incident signal, not its root cause. BuildDoctor returns the next evidence to collect, such as traces, structured logs, deployment changes, dependency health, and resource saturation.

## Prerequisites

- Python 3.10 or newer
- `pip` or another Python package installer
- An MCP-compatible client, such as an editor or desktop assistant

## Installation & Setup

From the repository root:

```bash
cd tools/build-doctor-mcp
python -m venv .venv
```

Activate the environment:

```bash
# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
.venv\\Scripts\\Activate.ps1

# Windows Command Prompt
.venv\\Scripts\\activate.bat
```

On Windows, `py -3 -m venv .venv` can be used instead of `python -m venv .venv` when the Python launcher is installed. On macOS and Linux, use `python3` if `python` is not available. The remaining commands are identical on all three platforms.

Install the server:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

The `.env.example` file documents the optional manifest size limit. The server does not require an API key.

## MCP Client Configuration

For a client that supports an MCP server configuration file, use an absolute path to the Python executable in the virtual environment:

```json
{
  "mcpServers": {
    "build-doctor": {
      "command": "/absolute/path/to/tools/build-doctor-mcp/.venv/bin/python",
      "args": ["-m", "build_doctor_mcp.server"]
    }
  }
}
```

On Windows, use the absolute path to `.venv\\Scripts\\python.exe`. Do not commit personal machine paths to this repository.

A portable starting configuration is available at [`examples/mcp-client-config.json`](examples/mcp-client-config.json). Replace the workspace placeholder with a real path. If the MCP client does not inherit the virtual environment, replace `python` with the absolute path to `.venv/bin/python` on macOS/Linux or `.venv\\Scripts\\python.exe` on Windows.

Client-specific presets and first-connection checks are available in [`examples/client-presets/README.md`](examples/client-presets/README.md) for VS Code, Cursor, and Claude Desktop.

Set an optional workspace boundary before starting the server:

```bash
# macOS/Linux
export BUILD_DOCTOR_ALLOWED_ROOT=/absolute/path/to/workspace

# Windows PowerShell
$env:BUILD_DOCTOR_ALLOWED_ROOT = "C:\\Users\\you\\workspace"

# Windows Command Prompt
set BUILD_DOCTOR_ALLOWED_ROOT=C:\\Users\\you\\workspace
```

## Configuration & Environment Variables

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `BUILD_DOCTOR_MAX_FILE_BYTES` | No | `200000` | Maximum bytes read from each recognized manifest |
| `BUILD_DOCTOR_MAX_LOG_CHARS` | No | `200000` | Maximum log characters analyzed |
| `BUILD_DOCTOR_MAX_REPORTS` | No | `20` | Maximum XML reports inspected per project |
| `BUILD_DOCTOR_ALLOWED_ROOT` | No | unset | If set, project paths must remain below this absolute workspace directory |
| `BUILD_DOCTOR_REQUIRE_ALLOWED_ROOT` | No | `false` | If `true`, project inspection fails unless an allowed workspace root is configured |
| `BUILD_DOCTOR_ALLOWED_TOOLS` | No | all | Comma-separated MCP tools to permit; unlisted tools fail closed |
| `BUILD_DOCTOR_WEBHOOK_SECRET` | No | unset | HMAC secret for gateway alert verification; never commit it |

## How to Run

Start the stdio server directly:

```bash
python -m build_doctor_mcp.server
```

The process waits for MCP messages on standard input and writes protocol messages to standard output. Use an MCP client to invoke its tools.

The Java ADK agent in `agents/build-doctor` can connect to this server through `BuildDoctorAgent.createWithMcp("python")`, which launches `python -m build_doctor_mcp.server` over stdio. Use the absolute path to the virtual-environment Python executable when the ADK process does not inherit your shell environment.

For a quick direct smoke check without an MCP client:

```bash
python -c "from build_doctor_mcp.server import analyze_failure; print(analyze_failure('error: cannot find symbol'))"
```

Analyze a provider-neutral alert directly:

```bash
python -c "import json; from build_doctor_mcp.server import analyze_alert; print(analyze_alert('new-relic', json.dumps({'event_type': 'latency', 'service': 'payments-api', 'value': 1200, 'threshold': 500, 'unit': 'ms'})))"
```

## Example Tool Input & Output

Input to `analyze_failure`:

```text
HTTP 401 response from the payments API
```

The response is JSON with this shape:

```json
{
  "schema_version": "1.1",
  "failure_type": "runtime-or-api",
  "confidence": "moderate",
  "evidence": ["HTTP 401 response from the payments API"],
  "scoring": {"matched_signals": ["http-status-or-transport"], "scores": {"runtime-or-api": 4}},
  "verification_status": "pending"
}
```

Classification is deterministic: matching rules emit stable signal IDs and weights, categories are ranked by total score, and confidence is capped when evidence is weak or categories tie. A probable cause requires multiple matching signals; root-cause status remains unconfirmed until a follow-up result. Structured test reports can corroborate test counts and failing test names. The model may explain the returned result, but it is not allowed to invent evidence or promote a pending verification to success.

For an ADK client, an optional smaller explanation model can be configured with `MODEL_NAME=gemma-3-4b-it` when the selected provider exposes Gemma 3 4B. The MCP server itself does not call a model: deterministic tools remain the authority, while Gemini or Gemma only explain their returned evidence.

## How to Test

```bash
python -m unittest discover -s tests -v
PYTHONPATH=src:. python evaluation/run.py
```

The tests run without an API key and verify generic failure analysis, multi-language manifest inspection, structured test reports, combined reports, guardrails, and missing-path handling. The evaluation command runs eighteen public cases across Python, TypeScript, Maven, Gradle, Rust, GitHub Actions, pytest, APIs, configuration, permissions, TLS, resources, schemas, CI, concurrency, timeouts, and ambiguous evidence; it exits non-zero if any expected signal or classification changes.

## Known Limitations

- Failure classification uses transparent signatures; it is not a replacement for ecosystem-specific report parsers.
- The server reads only a fixed list of root-level manifests and does not recursively scan repositories.
- The server does not run builds, tests, network calls, or remediation commands.
- XML reports are parsed with `defusedxml`; malformed or oversized reports are reported as unreadable or skipped.
- Recursive report discovery rejects resolved paths outside the selected workspace.
- Diagnostic output is redacted heuristically; do not treat redaction as a guarantee and review client permissions and supplied paths.

## Security & Privacy Considerations

- All operations are read-only.
- No shell commands or external network requests are made by the server.
- Logs and manifest reads are bounded by `BUILD_DOCTOR_MAX_LOG_CHARS` and `BUILD_DOCTOR_MAX_FILE_BYTES`.
- Set `BUILD_DOCTOR_ALLOWED_ROOT` to restrict inspection to a workspace directory.
- Set `BUILD_DOCTOR_REQUIRE_ALLOWED_ROOT=true` when an ungranted workspace must always be rejected.
- Set `BUILD_DOCTOR_ALLOWED_TOOLS` to grant only the MCP operations required by a client.
- Symlinked manifests are skipped.
- Webhook payloads must be HMAC-verified by the gateway before alert analysis.
- Suggested fixes are never executed, and verification remains `pending` until the client supplies a new result.
- Never include API keys, tokens, passwords, or private data in diagnostic logs sent to an MCP client.

## Future Improvements

- Add provider-specific webhook signature adapters behind an optional gateway.
- Add client-confirmed workspace roots and per-tool permission policies.
- Add per-tool permission policies and client-confirmed workspace grants.

## Completed MVP Milestones

- Deterministic signal scoring with confidence limits.
- Structured JUnit/Surefire/pytest-style report evidence.
- Before/after verification without command execution.
- Cross-platform MCP client presets.
- Eighteen public evaluation cases covering multiple ecosystems, CI formats, and operational failure categories.

## License

This project is contributed under the repository's MIT License.
