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

BuildDoctor is therefore a diagnostic gate and verification companion, not another autonomous code editor.

### Key Features

- `analyze_failure`: classify common compilation, dependency, test, runtime, and API failure signals.
- `inspect_project`: read bounded content from recognized project manifests without executing code.
- `summarize_diagnosis`: combine failure evidence and project metadata in one JSON response.
- `verify_resolution`: compare supplied before/after output and report `verified` only when deterministic success evidence is present.
- Versioned diagnostic responses with hypotheses, confidence, evidence gaps, remediation, and verification state.
- Deterministic signal IDs and scores make classification inspectable and reproducible for the same input.
- Standard MCP stdio transport for desktop and editor clients.
- Redaction, input limits, optional workspace allowlisting, and no automatic remediation.

## Technical Stack

- **Language & Runtime:** Python 3.10+
- **Protocol:** Model Context Protocol (MCP)
- **SDK:** Official Python MCP SDK
- **Transport:** stdio
- **Dependencies:** `mcp>=1.6,<2`

## Architecture & Data Flow

```text
[MCP client] <stdio> [BuildDoctor MCP server]
                              |
             +----------------+----------------+
             |                                 |
      [Failure analyzer]                [Manifest reader]
             |                                 |
             +----------> [Structured JSON evidence]
```

The server never runs project commands. The client supplies a log and, optionally, a project directory for bounded read-only inspection.

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
| `BUILD_DOCTOR_ALLOWED_ROOT` | No | unset | If set, project paths must remain below this absolute workspace directory |

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

Classification is deterministic: matching rules emit stable signal IDs and weights, categories are ranked by total score, and confidence is capped when evidence is weak or categories tie. A probable cause requires multiple matching signals; root-cause status remains unconfirmed until a follow-up result. The model may explain the returned result, but it is not allowed to invent evidence or promote a pending verification to success.

## How to Test

```bash
python -m unittest discover -s tests -v
```

The tests run without an API key and verify generic failure analysis, multi-language manifest inspection, combined reports, and missing-path handling.

## Known Limitations

- Failure classification uses transparent signatures; it is not a replacement for ecosystem-specific report parsers.
- The server reads only a fixed list of root-level manifests and does not recursively scan repositories.
- The server does not run builds, tests, network calls, or remediation commands.
- Diagnostic output is redacted heuristically; do not treat redaction as a guarantee and review client permissions and supplied paths.

## Security & Privacy Considerations

- All operations are read-only.
- No shell commands or external network requests are made by the server.
- Logs and manifest reads are bounded by `BUILD_DOCTOR_MAX_LOG_CHARS` and `BUILD_DOCTOR_MAX_FILE_BYTES`.
- Set `BUILD_DOCTOR_ALLOWED_ROOT` to restrict inspection to a workspace directory.
- Symlinked manifests are skipped.
- Suggested fixes are never executed, and verification remains `pending` until the client supplies a new result.
- Never include API keys, tokens, passwords, or private data in diagnostic logs sent to an MCP client.

## Future Improvements

- Add opt-in structured parsers for common test-report formats.
- Add explicit workspace roots and client-confirmed access policies.
- Add post-fix verification input without allowing the server to execute fixes.

## Next Four Steps

1. Add opt-in parsers for JUnit, Surefire, pytest, npm, Gradle, and CI report formats.
2. Add a verification tool that accepts a developer-supplied before/after result and compares it without executing commands.
3. Publish tested MCP client presets for common editors and desktop clients on macOS, Linux, and Windows.
4. Build a public evaluation fixture set measuring evidence accuracy, hypothesis quality, redaction, and verification honesty.

## License

This project is contributed under the repository's MIT License.
