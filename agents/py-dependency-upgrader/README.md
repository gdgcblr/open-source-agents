# Python Dependency Upgrader Agent

> Scan a Python repository for third-party packages, generate pytest smoke tests, and estimate the highest safe version each dependency can reach without breaking compatibility with the project's Python version.

---

## Overview

### Problem Statement
Software teams often inherit dependency drift: they can see what packages are installed, but they do not know which packages are actually in use, what test coverage exists for them, or which upgrade version is still compatible with the repo's Python runtime.

This project solves that by combining repository scanning, usage-aware test generation, changelog risk analysis, and version compatibility checks against PyPI metadata.

### Intended Users
- Python developers maintaining existing services and libraries
- Platform or SRE engineers reviewing dependency hygiene
- Open-source contributors checking upgrade safety before release

### Key Features
- Discovers third-party packages from standard dependency config files (`pyproject.toml`, `requirements*.txt`, nested requirement folders, and `-r` includes)
- Generates usage-aware pytest checks from repository call patterns
- Checks candidate versions compatible with the requested Python version using PyPI metadata
- Scans changelog/release-note links for migration and breaking-change markers before final safe-upgrade recommendation
- Validates upgrades step-by-step using ordered PyPI releases from current version, while skipping patch-only releases by default
- Creates temporary validation environments with `uv venv --python <requested-version>` and installs dependencies via `uv pip`
- Produces detailed failure diagnostics (stage, command, exit code, stdout/stderr tail)
- Shows tabular CLI output with Rich while preserving optional JSON output
- Exposes an ADK-based tool interface for agent usage

---

## Technical Stack
- **Language & Runtime**: Python 3.11+
- **Agent Framework / Core Library**: Google ADK
- **Models**: Any ADK-supported model (configurable via env)
- **External APIs / Tools**: PyPI JSON API, pytest, packaging library, uv

---

## Architecture & Data Flow

```text
[Repository Root] --> [Dependency Scanner]
                        |
                        +--> [PyProject / Requirements / Import Analysis]
                        |
                        +--> [Smoke Test Generator]
                        |
                        +--> [PyPI Compatibility + Changelog Risk Checker]
                                 |
                                 +--> [Stepwise Validation Runner (uv venv)]
                                            |
                                            +--> [JSON Report / pytest File]
```

The agent reads a repository, identifies third-party packages, writes usage-based tests under `tests/`, validates candidate upgrades step-by-step in temporary uv environments, and produces a recommendation with clear diagnostics.

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.11+
- `uv` installed
- Provider credentials configured for whichever ADK model backend you use

---

## Installation & Setup

1. Navigate to the project directory:

```bash
cd agents/py-dependency-upgrader
```

2. Install dependencies:

```bash
uv sync --dev
```

3. Configure environment variables (optional for ADK usage):

```bash
cp .env.example .env
```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `MODEL_NAME` | No | `gemini-2.5-flash` | ADK model identifier to use (provider-agnostic), for example `openai/gpt-4.1-mini` or `anthropic/claude-sonnet-4-6` |
| `ADK_MODEL` / `LLM_MODEL` | No | `None` | Optional fallback env names if `MODEL_NAME` is not set |
| Provider API key (for chosen backend) | Depends | `None` | Credentials needed by your selected model backend (for example `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`) |
| `LOG_LEVEL` | No | `info` | Logging verbosity |

---

## How to Run

Scan the current repository and show tabular report output:

```bash
uv run python main.py --repo .
```

Show JSON in console (instead of table):

```bash
uv run python main.py --repo . --console-output json
```

Show both table and JSON in console:

```bash
uv run python main.py --repo . --console-output both
```

Write the JSON result to a file (keeps table output in console by default):

```bash
uv run python main.py --repo . --output dependency-report.json
```

Run only specific packages:

```bash
uv run python main.py --repo . --package requests,pandas
```

Limit how many discovered packages are processed:

```bash
uv run python main.py --repo . --limit 5
```

---

## Example Input & Output

### Example Input

```text
Analyze the repository in the current directory and show upgrade-safe versions for the dependencies it uses.
```

### Example Output

```json
{
  "project_root": "/path/to/project",
  "package_count": 4,
  "generated_test_file": "/path/to/project/tests/test_generated_dependency_smoke.py",
  "safe_upgrade_report": [
    {
      "package": "requests",
      "current_version": "2.31.0",
      "metadata_candidate_version": "2.32.2",
      "tested_upgrade_version": "2.32.2",
      "recommended_upgrade_version": "2.32.2",
      "status": "ok"
    }
  ]
}
```

Field meaning:
- `metadata_candidate_version`: best candidate from PyPI metadata and Python compatibility filters
- `tested_upgrade_version`: highest version that passed generated repo-usage validation
- `recommended_upgrade_version`: final recommendation after validation + changelog risk checks
- `version_checks`: per-version execution records including changelog risk, runtime info, and failure details when applicable

---

## How to Test

```bash
uv run pytest
```

This project includes focused unit tests for dependency discovery and safe-upgrade calculation.

---

## Known Limitations
- The generated tests are usage-informed but still heuristic; they do not replace a full project test suite.
- If the requested Python runtime cannot be resolved locally and `uv` is unavailable, validation is skipped with an explicit reason.
- Changelog analysis is keyword-based and may miss nuanced breaking changes.

---

## Security & Privacy Considerations
- No secrets are committed.
- The agent only reads local project files and queries public PyPI metadata.
- The generated tests are local smoke checks and do not execute arbitrary user-supplied code beyond standard Python import checks.

---

## Future Improvements
- [ ] Add compatibility checks for Python version ranges and major-version breakage heuristics
- [ ] Support Poetry and PDM lockfile analysis
- [ ] Generate package-specific test templates using static API discovery
- [ ] Add automatic PR-ready upgrade notes and changelog summaries

---

## License

This project is contributed under the repository's open-source license.
