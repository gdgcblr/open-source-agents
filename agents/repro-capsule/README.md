# ReproCapsule

> Reproduce Python bug reports with explicit, constrained test execution and replayable evidence—without giving an LLM shell access.

## Overview

### Problem statement and intended users

Open-source maintainers and developers lose time translating incomplete bug reports into reproducible failures. Reproduction is also hard to review: the report, environment, command, and test output often live in different places. ReproCapsule inspects a repository, explains what evidence it found, and can run one fixed test command inside a network-isolated, read-only Docker container after the user explicitly opts in. It saves the outcome as a portable JSON capsule that another developer can replay.

### Key features

- **Read-only investigation:** Gemini can list files, search text, and read bounded files. It has no repository write, shell, or test-execution tool. Common credential files (`.env*`, key/certificate files, and service-account JSON files) are hidden from its repository tools.
- **Execution control:** No target-repository code runs unless `--allow-execution` is supplied. The only command is Python `unittest` discovery in Docker with a read-only source mount, no network, dropped capabilities, and resource limits.
- **Replayable evidence:** A versioned capsule records the issue hash, repository commit when available, fixed command, image, isolation settings, status, and bounded output. Capsule content cannot choose the command.
- **Offline demo:** `run.ps1 demo` or `bash ./run.sh demo` runs a bundled, intentionally failing fixture locally without an API key or Docker. Its capsule is labeled `local_demo` and is not a container-isolation claim or replay capsule.

### What makes ReproCapsule different

Many issue-triage agents stop after identifying likely files or drafting reproduction steps. ReproCapsule's distinctive step is the optional, user-authorized test run: the host invokes one fixed `unittest` command in Docker, then records the repository revision and bounded output in a capsule that can be replayed. The model never gets shell access and cannot select the command.

## Technical stack

- **Language/runtime:** Python 3.11+
- **Agent core:** Small standard-library Gemini `generateContent` function-calling loop; no agent framework dependency.
- **Model:** Gemini 3.8 Flash by default; override with `GEMINI_MODEL`. The Gemini API offers free and paid tiers with different quotas and data terms; review the current [billing](https://ai.google.dev/gemini-api/docs/billing) and [pricing](https://ai.google.dev/gemini-api/docs/pricing) information before using it.
- **Execution runtime:** Pre-pulled `python:3.12-slim` Docker image.
- **External services:** Google Gemini API only for model-assisted investigation. Demo and unit tests are offline.

## Architecture and data flow

```text
Issue report + repository path
      -> Gemini investigation loop (bounded, read-only tools)
      -> user opts into execution with --allow-execution
      -> fixed unittest command in Docker (no network, RO source)
      -> versioned JSON capsule -> replay using same fixed runner
```

The model cannot execute tests or choose commands. The host runner owns the allowlist and isolation flags. Each investigation is limited to four model tool turns plus a final synthesis request, eight tool calls, 8,000 report characters, and 80,000 characters of repository tool output. Replaying repeats the fixed test command; it does not install dependencies or recreate an arbitrary environment.

## Prerequisites

- Python 3.11 or newer. The launcher creates `.venv`; the agent itself uses only Python standard-library modules.
- Docker Desktop (Windows/macOS) or Docker Engine (Linux), installed and running only when you opt into test execution with `--allow-execution`.
- A Gemini API key only for `investigate`. The launcher prompts with hidden input when needed. `demo` and the test suite need no API key.
- Internet access on first authorized execution to pull `python:3.12-slim`; the test container itself has no network access.

The launcher prepares the Python environment and pulls the test image for you. Python and the container runtime are host-level prerequisites and cannot safely be installed or started by a repository script. Investigation without execution and the demo do not require Docker.

Install prerequisites from their official sources if needed: [Python](https://www.python.org/downloads/), [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/), or [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/). Start Docker Desktop once before using `--allow-execution`.

## One-command start

From the repository root, run one command. First use creates `.venv`; there are no Python packages to install.

```powershell
# Windows PowerShell
.\agents\repro-capsule\run.cmd demo
.\agents\repro-capsule\run.cmd investigate --repo C:\src\project --report C:\src\bug-report.md
```

```bash
# macOS / Linux (bash is included with macOS; no chmod needed)
bash ./agents/repro-capsule/run.sh demo
bash ./agents/repro-capsule/run.sh investigate --repo /src/project --report /src/bug-report.md
```

To open the local visual dashboard, run `ui` instead of `demo`:

```powershell
.\agents\repro-capsule\run.cmd ui
```

```bash
bash ./agents/repro-capsule/run.sh ui
```

The dashboard binds only to `127.0.0.1`, opens your browser, and shows a real offline run of the agent-owned fixture plus its generated capsule. It does not need an API key or Docker. Its sample button never runs code from a repository you choose; actual repository execution still requires the CLI's explicit `--allow-execution` flag.

To authorize test execution, add `--allow-execution` to the investigation command. The launcher checks that Docker is running and pulls the fixed Python image if needed. On Windows it resolves Docker Desktop even when its CLI is not on `PATH`.

Alternatively, copy `agents/repro-capsule/.env.example` to `agents/repro-capsule/.env` and add `GEMINI_API_KEY=...` to avoid the hidden prompt. The CLI loads this local file automatically; `.env` is ignored by Git. Do not share or commit it. `run.cmd` works from PowerShell and Command Prompt.

## Configuration

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `GEMINI_API_KEY` | For investigation | Prompted if missing | Google AI Studio key. Only the issue report and tool results are sent to Gemini. |
| `GEMINI_MODEL` | No | `gemini-3.8-flash` | Gemini model identifier. |

## How to run

Run commands from the repository root. Start with the offline demo:

```powershell
.\agents\repro-capsule\run.cmd demo
```

Investigate a report without running repository code (model analysis only):

```powershell
.\agents\repro-capsule\run.cmd investigate --repo C:\src\project --report C:\src\bug-report.md
```

Only after reviewing the investigation, explicitly authorize fixed test execution:

```powershell
.\agents\repro-capsule\run.cmd investigate --repo C:\src\project --report C:\src\bug-report.md --allow-execution --output C:\src\repro-capsule.json
```

Replay the recorded fixed command against the same checkout (requires the same explicit authorization). Replay blocks if the recorded Git revision differs or cannot be verified. To knowingly replay another revision, add `--allow-revision-mismatch`:

```powershell
.\agents\repro-capsule\run.cmd replay --repo C:\src\project --capsule C:\src\repro-capsule.json --allow-execution
```

macOS/Linux commands use `bash ./agents/repro-capsule/run.sh` with the same subcommands and flags. For example:

```bash
bash ./agents/repro-capsule/run.sh investigate --repo /src/project --report /src/bug-report.md --allow-execution --output /src/repro-capsule.json
bash ./agents/repro-capsule/run.sh replay --repo /src/project --capsule /src/repro-capsule.json --allow-execution --allow-revision-mismatch
```

`investigate` requires `GEMINI_API_KEY`. A failed test run is a valid result and is recorded in the capsule. For authorized execution, the launcher checks Docker and pulls `python:3.12-slim` if it is missing; the container run itself has no network.

## End-to-end example

The bundled sample repository contains a real, intentionally buggy parser: `parse_timeout(0)` incorrectly returns the default because the implementation uses `value or default`. Its test suite has one passing test and one expected failure. This example demonstrates the complete analysis, authorized Docker run, capsule, and replay flow.

From the repository root, first inspect without running the sample repository's code:

```powershell
.\agents\repro-capsule\run.cmd investigate --repo .\agents\repro-capsule\examples\timeout-bug-repo --report .\agents\repro-capsule\examples\bug-report.md
```

After reviewing the model's analysis, explicitly authorize the fixed Docker test run and write its capsule:

```powershell
.\agents\repro-capsule\run.cmd investigate --repo .\agents\repro-capsule\examples\timeout-bug-repo --report .\agents\repro-capsule\examples\bug-report.md --allow-execution --output .\agents\repro-capsule\capsules\timeout-bug.json
```

Replay that evidence against the same checkout and revision:

```powershell
.\agents\repro-capsule\run.cmd replay --repo .\agents\repro-capsule\examples\timeout-bug-repo --capsule .\agents\repro-capsule\capsules\timeout-bug.json --allow-execution
```

On macOS/Linux, use `bash ./agents/repro-capsule/run.sh` with the same arguments. The report-analysis commands require a Gemini API key; test execution and replay require Docker. The expected test result is one failure (`test_explicit_zero_is_preserved`) and one pass. This is a genuine sample-repository run; the exact Gemini analysis text varies by model response. The earlier `demo` command remains an offline onboarding demo and does not exercise model analysis or Docker.

## Example input and output

Input: `examples/bug-report.md` describes a configuration parser that replaces an explicit `timeout=0` with a default. The exact model analysis depends on repository contents and Gemini response. A capsule has this shape:

```json
{
  "schema_version": 1,
  "repository_revision": "<git commit or null>",
  "issue_sha256": "<sha256 of report>",
  "execution": {
    "mode": "container",
    "status": "failed",
    "exit_code": 1,
    "command": ["python", "-m", "unittest", "discover", "-v"],
    "image": "python:3.12-slim",
    "network": "disabled",
    "repository_mount": "read-only",
    "stdout": "<bounded output>",
    "stderr": "<bounded output>"
  }
}
```

This capsule is a schema illustration, not a claimed live Gemini or Docker run. The offline `demo` prints a genuine run of its bundled, locally executed onboarding fixture; the end-to-end sample above is the Docker reproduction example.

## How to test

From the agent directory, install the development extra and run the same checks on Windows, macOS, or Linux:

```text
python -m pip install -e ".[dev]"
python -m ruff check .
python -m unittest discover -s tests -v
```

Then run the appropriate launcher from the repository root (`.\agents\repro-capsule\run.cmd demo` on Windows or `bash ./agents/repro-capsule/run.sh demo` on macOS/Linux).

Tests verify path traversal rejection, credential-like file filtering, allowlisted model tools, opt-in behavior, bounded output capture, timeout cleanup, fixed Docker isolation arguments, replay revision checks, and capsule tamper rejection. Unit tests mock Gemini and Docker. The offline demo validates launcher startup and evidence formatting but does not validate isolation. A cross-platform CI workflow example is provided at `ci/github-actions.workflow.example.yml`; copy it into the host repo's `.github/workflows/` because GitHub does not discover workflows nested in an agent folder. The workflow exercises Python 3.11+ on Windows, macOS, and Linux.

## How we will prove value

Evaluate a small set of real, permissioned Python issues with known fixes. Track (1) fraction reproduced on the first run, (2) maintainer time from report to verified reproduction, (3) capsule replay match rate on a second machine, and (4) unsupported reproduction claims (target: zero). Compare against maintainers' normal manual workflow; publish the fixture set and methodology, not private issue data. This initial release is a prototype and includes no benchmark claim.

## Known limitations

- Test runner support is currently Python standard-library `unittest` discovery only. It does not install dependencies, set up databases, or emulate the reporter's OS.
- The offline demo runs only its agent-owned fixture locally to verify onboarding and evidence formatting. It does not execute repository code and its capsule cannot be replayed.
- Docker is required for actual repository execution. We exercised the Windows Docker replay path during development; macOS Intel and Apple Silicon Docker setups are documented but should still be confirmed in CI/on contributor hardware.
- Replay records the Docker image tag, not its immutable registry digest or the target project's dependency environment. Results can differ if the image or repository setup changes.
- Gemini analysis can be wrong or incomplete; tool output and reports sent to Gemini may contain source code or sensitive bug details. Review before use.
- CI mocks Gemini; live API availability, quota, privacy terms, and billing depend on the operator's Google AI account and are not asserted by the offline suite.
- Capsule replay compares status and exit code, not semantic equivalence. A known Git revision mismatch blocks by default; the explicit override marks revision verification as overridden.
- A read-only bind mount prevents source edits but is not a substitute for running untrusted code on a disposable host. Use a trusted Docker installation and review the repository first.
- The `python:3.12-slim` runtime currently supports only standard-library `unittest` projects; dependency installation and project-specific services are deliberately not automated.

## Security and privacy

- No arbitrary shell execution, writes, package installation, or network access are exposed to the model.
- Repository code is mounted read-only and runs as an unprivileged container user with dropped capabilities and limits. Filename-based filters hide common credential files from model tools, but they are not a complete secret scanner; review the data that can be sent to Gemini.
- Test execution is disabled unless the operator passes `--allow-execution`.
- Model-assisted runs transmit the issue report and any files the model requests to Google's Gemini API. Do not use with private code or sensitive data unless your organization's policy permits it.
- The issue report itself is not stored in the capsule; only its SHA-256 digest is saved. Test output and model analysis may contain sensitive strings, so review capsules before sharing.

## Future improvements

- [ ] Add explicit runner adapters for pytest and common project environments.
- [ ] Capture and compare normalized failing test identifiers across replays.
- [ ] Add a public evaluation corpus with maintainer-approved issues and measured baseline.
- [ ] Add local model providers and configurable redaction before remote inference.
- [ ] Support repository-specific setup manifests without enabling model-authored commands.

## License

This project is contributed under the repository's open-source license.
