# mcp-behavior-diff

> Detect behavior changes in an MCP server that schema diffs cannot see, by running the same read-only tool calls against an old and a new version and diffing the results.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Existing MCP diff tools compare the *advertised schema* (`tools/list`). A server can keep an identical schema while its behavior changes (different wording, different numbers, different error handling), and agents that depend on it break silently.
- **Intended Users**: MCP server authors and teams that upgrade MCP servers and want a CI check for behavior regressions.

### Key Features
- Runs fixture-defined tool calls against `old` and `new` servers over stdio and diffs normalized results.
- **Security-first by default** (see [Security & Privacy Considerations](#security--privacy-considerations)): explicit per-call `read_only: true` assertion, destructive tools never called, scrubbed environment, hard limits, output sanitising and secret redaction, execution confirmation.
- Deterministic exit codes for CI. No LLM and no API key needed.

> **Status: v0.1 (guardrails + core loop).** Exact-match comparison only. Ignoring volatile fields, HTTP transports and richer reports are planned, see [Future Improvements](#future-improvements).

---

## Technical Stack

- **Language & Runtime**: Python 3.11+
- **Core Library**: Model Context Protocol Python SDK (`mcp` 2.x, stdio client) and PyYAML (`safe_load` only)
- **Models**: none
- **External APIs / Tools**: none

---

## Architecture & Data Flow

```
fixture.yaml --> [loader: strict validation, hard ceilings]
                       |
                       v
          [confirm: show commands that will run]
                       |
        for each of old, new server:
          spawn (no shell, scrubbed env, private stderr)
            --> tools/list --> [policy: gate each call] --> tools/call (timeout)
            --> [sanitise -> redact -> truncate] --> CallRecord
                       |
                       v
              [diff old vs new] --> text report / JSON report / exit code
```

---

## Prerequisites

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `pip`
- Nothing else. No API keys.

---

## Installation & Setup

```bash
cd tools/mcp-behavior-diff
uv venv --python 3.13 .venv        # any Python >= 3.11 works
uv pip install --python .venv/bin/python -e ".[dev]"
```

(With plain pip: `python -m venv .venv && .venv/bin/pip install -e ".[dev]"`.)

---

## Configuration & Environment Variables

None required. See `.env.example` for how to pass credentials to the server under test safely.

### Fixture format (`version: 1`)

```yaml
version: 1
servers:
  old: {command: python, args: [toy_server.py, v1]}   # one executable + args, never a shell string
  new: {command: python, args: [toy_server.py, v2]}   # cwd defaults to the fixture's directory
calls:
  - id: greet-world
    tool: greet
    arguments: {name: World}
    read_only: true          # REQUIRED: you assert this call has no side effects
limits:                       # optional; may lower, never exceed, the hard ceilings
  call_timeout_s: 10
  max_calls: 50
```

Optional per-server keys: `cwd` (must stay inside the fixture directory), `env` (literal, non-secret values), `env_passthrough` (names of variables to copy from your shell).

---

## How to Run

```bash
cd examples/toy_server
mcp-behavior-diff check fixture.yaml          # validate only; executes nothing
mcp-behavior-diff diff fixture.yaml           # asks for confirmation, then runs
mcp-behavior-diff diff fixture.yaml --yes     # non-interactive (CI)
mcp-behavior-diff diff fixture.yaml --yes --json-out report.json
```

Exit codes: `0` no change, `1` behavior changed, `2` usage / policy error, `3` incomplete (some calls were refused, skipped, timed out, errored or named a tool the server does not have, on both sides, so "no change" cannot be claimed).

---

## Example Input & Output

Real output from `examples/toy_server/fixture.yaml` (v2 of the toy server adds `!` to `greet`; the schema is identical):

```
[=] add-basic  (add)  identical  (ok)
[~] greet-world  (greet)  CHANGED  old=ok new=ok
      --- old
      +++ new
      @@ -3,10 +3,10 @@
           "content": [
             {
      -        "text": "Hello, World",
      +        "text": "Hello, World!",
               "type": "text"
             }
           ],
           "structured": {
      -      "result": "Hello, World"
      +      "result": "Hello, World!"
           }
         },
[=] leak-check  (leak)  identical  (ok)

3 call(s): 1 changed, 0 not executed
```

---

## How to Test

```bash
.venv/bin/python -m pytest -q
```

Tests include real subprocess runs against the toy server and prove, among other things, that a destructive tool is never invoked and that parent-process secrets never reach the server.

---

## Known Limitations

- Exact comparison only: timestamps, ids and other volatile output will be reported as changes (ignore rules are planned).
- stdio transport only. No HTTP/SSE servers.
- Tests and docs verified on macOS with Python 3.13 and `mcp` 2.3.0; Linux and Windows are untested. `mcp` 2.x changed APIs from 1.x, so the dependency is pinned to `>=2,<3`.
- A tool that has side effects but is *declared and asserted* read-only will still be called. Correctness of `read_only: true` is your responsibility.
- Redaction is best-effort pattern matching, not a guarantee: review reports before sharing them.
- Only text content is compared; images, audio and embedded resources are recorded by type only.
- The toy server's fake credential is assembled at runtime so no secret-looking literal lives in the repo.

---

## Security & Privacy Considerations

**This tool executes the commands in your fixture. It is not a sandbox.** A fixture is code: only run fixtures you trust, as you would a shell script. The guardrails below limit accidents and hostile *server output*; they do not defend against a malicious fixture or a malicious server binary you chose to run.

- **Consent**: the exact commands are printed and confirmation is required (`--yes` in non-interactive sessions).
- **No shell**: commands run as `argv`; shell syntax in `command` is rejected.
- **Fail-closed tool gating**: a call runs only if the fixture sets `read_only: true`, the tool is advertised by the server, and the server does not declare it destructive or non-read-only. Server annotations can veto but never grant permission.
- **Environment**: the server gets the MCP SDK's minimal inherited set (`HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM`, `USER`) plus only what the fixture lists. Secret-looking names need `--allow-secret-env`; loader-hijack variables (`LD_*`, `DYLD_*`, `PATH`, ...) are rejected; passed-through values are scrubbed from all output.
- **Limits**: per-call and startup timeouts, max calls, argument and output size, all with hard ceilings. After a timeout the remaining calls are skipped.
- **Untrusted output**: terminal escapes and control characters are stripped, invisible/bidi Unicode is made visible, credential-like strings are redacted (by shape, and by key name such as `password`/`token`/`api_key`, including inside JSON text), text is size-capped. Values under secret-looking keys are replaced by a per-run fingerprint, so a *changed* secret still shows as a change but its value is never stored. Server stderr is kept in a private temp file and only shown (sanitised) when startup fails.
- **Server-initiated requests**: sampling, elicitation and roots callbacks are not registered, so the server cannot ask this client for anything.
- **Reports**: written only to the path you pass, never overwritten without `--force`, never through a symlink. Cleaned data only.
- **Data privacy**: nothing leaves your machine; there is no network code in this tool.

---

## Future Improvements

- [ ] Ignore/normalize rules for volatile fields (JSONPath).
- [ ] Optional tool-call-level opt-in for side-effecting tools in disposable environments.
- [ ] Streamable HTTP transport with host allow-listing.
- [ ] Markdown / SARIF reports and a GitHub Action.
- [ ] Record mode to generate a fixture from `tools/list`.

---

## Sample Input and Output

See [Sample_Demo.md](Sample_Demo.md) for a full walkthrough of the toy-server demo: the fixture input, `check` output, the `diff` text report, the JSON report (including secret redaction) and what each exit code means.
