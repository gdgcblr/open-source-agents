# Contribution Review Agent

> A two-layer PR audit tool that mechanically checks every contribution against the monorepo rules — deterministically in Layer 1 (no API key needed) and semantically in Layer 2 (Google ADK + Gemini).

---

## Overview

### Problem Statement & Intended Users

- **Problem**: Maintainers of community AI monorepos must manually verify every pull request against the same checklist — naming conventions, template completeness, secret hygiene, scope isolation, env-var documentation, and dependency manifests. This is slow, error-prone, and causes contributors to be rejected for avoidable mechanical misses.
- **Intended Users**: **Contributors** (pre-flight self-check before opening a PR) and **maintainers** (triage and first-pass review automation).

This tool does **not** judge which project is "best". It removes mechanical checking and produces a structured summary; humans judge quality and creativity.

### Key Features

- **Layer 1 — Deterministic Auditor** (zero API key): eleven rules covering structure, naming, required files, README completeness, secret scanning, file hygiene, git scope, and dependency declarations. Runs offline with the Python standard library only.
- **Layer 2 — ADK Agent** (optional Gemini key): wraps Layer 1 and adds semantic observations — undocumented env vars, fabricated example outputs, README commands that don't match code — without overriding the deterministic verdict.
- **CLI**: `python -m contrib_audit check <path>` for local projects; `python -m contrib_audit triage --repo OWNER/NAME` for GitHub PR triage (no clone, read-only, rate-limit aware).

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: [Google ADK](https://google.github.io/adk-docs/) (Layer 2 only); standard library `urllib` for all HTTP (no `requests`)
- **Models**: `gemini-flash-latest` (default); `gemini-2.5-flash` supported
- **External APIs / Tools**: GitHub REST API (read-only, optional GITHUB_TOKEN, for `triage`); Google Gemini API (optional, for Layer 2)

---

## Architecture & Data Flow

```
[User / CI]
    │
    ├─► python -m contrib_audit check <path>          Layer 1 only
    │       │
    │       └─► rules/  (R01-R11, stdlib only)
    │               │
    │               └─► AuditResult ──► render_text / render_markdown / render_json
    │
    └─► adk run review_agent  /  adk web --port 8000   Layer 1 + Layer 2
            │
            └─► LlmAgent (Gemini)
                    │
                    ├─► run_static_review()   ──► rules/ (deterministic verdict)
                    ├─► list_project_files()  ──► filesystem (read-only, repo-scoped)
                    └─► read_project_file()   ──► filesystem (128 KB cap, secrets redacted)
                            │
                            └─► Semantic observations (no verdict change)
```

**Triage flow** (no clone):

```
python -m contrib_audit triage --repo OWNER/NAME
    │
    └─► GitHub REST API (urllib)
            ├── List open PRs
            ├── Fetch changed file list + patches
            └── Apply rules R01-R07, R09, R10 to patches
                    └─► Ranked table (REJECT → READY)
```

---

## Prerequisites

- Python 3.10 or newer
- `pip` (or `uv`)
- **Layer 1 CLI**: no API key required
- **Layer 2 (ADK agent)**: `GOOGLE_API_KEY` from [Google AI Studio](https://aistudio.google.com/app/apikey)
- **Triage**: internet access; optional `GITHUB_TOKEN` for higher rate limits

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/contribution-review-agent
   ```

2. **Set up the virtual environment and install dependencies:**
   ```bash
   python -m venv .venv

   # Windows:
   .venv\Scripts\activate
   # Linux / macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   ```bash
   cp .env.example .env
   # Edit .env and fill in GOOGLE_API_KEY (required only for Layer 2)
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | No* | *None* | Gemini API key. Required only for the ADK agent (Layer 2). Layer 1 CLI works with no key. |
| `MODEL_NAME` | No | `gemini-flash-latest` | Gemini model identifier (e.g. `gemini-flash-latest`, `gemini-2.5-flash`). |
| `GITHUB_TOKEN` | No | *None* | Read-only GitHub personal access token. Without it, the `triage` command gets 60 req/hr; with it, 5 000 req/hr. Never required. |

*Layer 2 agent requires `GOOGLE_API_KEY`.

---

## How to Run

### Layer 1 — Local folder audit (no API key)

```bash
# From agents/contribution-review-agent/
python -m contrib_audit check .

# Audit any project folder, auto-detect repo root:
python -m contrib_audit check agents/my-cool-agent

# Explicit repo root + markdown output:
python -m contrib_audit check agents/my-cool-agent \
    --repo-root /path/to/open-source-agents \
    --format markdown

# JSON output (useful for CI):
python -m contrib_audit check . --format json

# Exit code: 0 = READY / APPROVE_WITH_NITS, 1 = CHANGES_REQUESTED / REJECT
```

### Triage open PRs on GitHub (no API key required, no clone)

```bash
python -m contrib_audit triage --repo gdgcblr/open-source-agents --limit 10
```

### Layer 2 — ADK agent (needs GOOGLE_API_KEY in .env)

```bash
# Terminal chat:
adk run review_agent

# Web UI at http://localhost:8000:
adk web --port 8000
```

In the agent, type a message like:
```
Review the project at agents/contribution-review-agent
```

---

## Example Input & Output

### Layer 1 — CLI check (real run, this folder)

**Command:**
```bash
python -m contrib_audit check . --format text
```

**Output:**
```
  Contribution Review — contribution-review-agent
  Path: /Users/reddygopalkrishna/Public/gdg-open-source/open-source-agents/agents/contribution-review-agent

  Verdict: READY

  No findings — all checks passed!
```

### Layer 1 — JSON output

**Command:**
```bash
python -m contrib_audit check . --format json
```

**Output (truncated):**
```json
{
  "project_path": ".../agents/contribution-review-agent",
  "project_name": "contribution-review-agent",
  "verdict": "READY",
  "findings": []
}
```

### Layer 2 — ADK agent (real run, requires GOOGLE_API_KEY)

**Input Prompt:**
```text
Review the project at agents/contribution-review-agent
```

**Agent Response:**
```markdown
### Verdict
READY

### Blocking Issues
None

### Suggested Fixes
None required.

### Semantic Observations
- **Workflow & Commands**: Installation commands (`pip install -r requirements.txt`) and run commands (`python -m contrib_audit check .`) exactly match the files present in the repo.
- **Dependencies**: All third-party Python imports (`google`, `dotenv`) are explicitly declared in `requirements.txt`.
- **Honest Documentation**: The example output sections represent real command executions with zero synthetic placeholders.
- **Security & Limitations**: The project explicitly addresses regex scanning limits, patch truncation caveats, and API rate-limiting handling.
```

---

## How to Test

```bash
# From agents/contribution-review-agent/ with .venv active:
pytest tests/ -v
```

All tests are fully offline — no API key needed. Fake secrets are built at runtime from string fragments; no real credentials are ever present in the test fixtures.

Expected result: all tests pass. Example:

```
tests/test_cli_and_report.py ... PASSED  (9 tests)
tests/test_rules_r01_r06_r10.py ... PASSED  (23 tests)
tests/test_rules_r07_r08_r11.py ... PASSED  (19 tests)
tests/test_triage.py ... PASSED  (7 tests)
============================== 58 passed in 0.62s ==============================
```

---

## Known Limitations

- **False positives/negatives in secret detection**: The regex patterns in R07 are heuristic. They will miss novel secret formats and may flag legitimate-looking strings. This is **not a replacement for a real secret scanner** (e.g. truffleHog, GitHub secret scanning, or `git-secrets`).
- **Triage reads patches only**: The `triage` command fetches GitHub diff patches, which may be truncated by the API for large PRs. Findings on truncated diffs will be incomplete.
- **Semantic observations depend on the model**: Layer 2 notes are generated by Gemini and may contain hallucinations or miss issues. The deterministic verdict from Layer 1 is always authoritative.
- **Free-tier rate limits**: The Gemini free tier (AI Studio) has per-minute token limits. Large reviews may hit these. The agent uses at most 2 model calls per review to mitigate this.
- **Google data-use caveat**: When using AI Studio (free tier), prompts may be used to improve Google products. Use Vertex AI or a paid tier for sensitive code.
- **GitHub API rate limits**: Without `GITHUB_TOKEN`, the `triage` command is limited to 60 requests/hour. With a token: 5 000/hour. The CLI prints a clear message and the reset time when the limit is hit.
- **Scope check requires git**: R09 needs `git` in PATH and a reachable `upstream/main` or `origin/main`. When unavailable, the check is skipped and reported as INFO.
- **R11 (import check) is a stretch rule**: It uses AST parsing and name normalisation. False warnings can occur with namespace packages or unusual install names.
- **Tested on**: macOS 14 (Sonoma) and Ubuntu 22.04. Windows support is implemented using `pathlib` throughout (no shell-specific code), but has not been fully tested end-to-end.

---

## Security & Privacy Considerations

- **Secrets handling**: Credentials are loaded exclusively from `.env` via `python-dotenv`. The `.env` file is covered by `.gitignore` and is never committed. `.env.example` contains only placeholder strings.
- **Read-only tools**: All three agent function tools (`run_static_review`, `list_project_files`, `read_project_file`) are strictly read-only. They block path traversal by resolving paths and verifying they sit inside the repo root before any I/O.
- **Evidence redaction**: R07 findings and anything returned to the LLM by `read_project_file` have secrets redacted (first 4 chars + ellipsis or `[REDACTED]`) before being surfaced.
- **No code execution**: The agent never executes contributed code. It reads file contents and runs deterministic Python logic only.
- **No writes to GitHub**: The `triage` command calls the GitHub REST API with GET requests only. No write endpoints are used.
- **Data privacy**: File content and README text are sent to the Gemini API when Layer 2 is active. Avoid using Layer 2 on projects containing proprietary or sensitive information. Use Vertex AI for production/private use.

---

## Related Work

Similar ideas exist in the ecosystem:
- **GitHub Next "Agentics" Contribution Check** workflow: a CI-based approach using GitHub Actions.
- **[Danger](https://danger.systems/)** and **Danger-JS/danger-swift**: widely used PR linting frameworks.
- **GitHub Secret Scanning**: GitHub's built-in push-protection and secret scanning.

**How this differs**: `contribution-review-agent` enforces *repo-specific* deterministic rules (not generic linters), requires **zero API key for the core layer**, needs **no CI setup** (runs as a local pre-flight), performs **static-only analysis** (never executes contributed code), and is designed for contributor self-service before opening a PR. No code was copied from any of the above projects.

---

## Future Improvements

- [ ] Cache GitHub API responses to reduce rate-limit pressure during triage.
- [ ] Support Vertex AI as the model backend for Layer 2 (avoids AI Studio data-use caveat).
- [ ] Add streaming responses to the ADK agent.
- [ ] GitHub Actions workflow template so maintainers can run Layer 1 in CI with zero setup.
- [ ] Extend R07 with entropy-based detection for high-entropy strings.
- [ ] Windows end-to-end testing in CI.

---

## License

*This project is contributed under the repository's open-source license.*
