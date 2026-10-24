# BuildDoctor MCP Server

> A read-only Model Context Protocol server that gives any MCP-compatible client evidence-based diagnosis for build, test, runtime, and API failures.

## Overview

### Problem Statement & Intended Users

Failure diagnosis is slow when logs are large, symptoms are misleading, and project context is scattered across manifests. This server exposes safe diagnostic tools that work with any language, build system, framework, or API because they accept evidence rather than assuming one ecosystem.

Intended users include developers, open-source contributors, students, support engineers, and AI assistants connected through MCP.

### Key Features

- `analyze_failure`: classify common compilation, dependency, test, runtime, and API failure signals.
- `inspect_project`: read bounded content from recognized project manifests without executing code.
- `summarize_diagnosis`: combine failure evidence and project metadata in one JSON response.
- Standard MCP stdio transport for desktop and editor clients.
- No API key, database, shell execution, file mutation, or external service required.

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
```

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

## Configuration & Environment Variables

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `BUILD_DOCTOR_MAX_FILE_BYTES` | No | `200000` | Maximum bytes read from each recognized manifest |

## How to Run

Start the stdio server directly:

```bash
python -m build_doctor_mcp.server
```

The process waits for MCP messages on standard input and writes protocol messages to standard output. Use an MCP client to invoke its tools.

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
  "failure_type": "runtime-or-api",
  "confidence": "moderate",
  "evidence": ["HTTP 401 response from the payments API"],
  "verification_status": "pending"
}
```

## How to Test

```bash
python -m unittest discover -s tests -v
```

The tests run without an API key and verify generic failure analysis, multi-language manifest inspection, combined reports, and missing-path handling.

## Known Limitations

- Failure classification uses transparent signatures; it is not a replacement for ecosystem-specific report parsers.
- The server reads only a fixed list of root-level manifests and does not recursively scan repositories.
- The server does not run builds, tests, network calls, or remediation commands.
- Diagnostic output may contain sensitive log or manifest content; review client permissions and supplied paths.

## Security & Privacy Considerations

- All operations are read-only.
- No shell commands or external network requests are made by the server.
- Manifest reads are bounded by `BUILD_DOCTOR_MAX_FILE_BYTES`.
- Symlinked manifests are skipped.
- Never include API keys, tokens, passwords, or private data in diagnostic logs sent to an MCP client.

## Future Improvements

- Add opt-in structured parsers for common test-report formats.
- Add explicit workspace roots and client-confirmed access policies.
- Add post-fix verification input without allowing the server to execute fixes.

## License

This project is contributed under the repository's MIT License.
