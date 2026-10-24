# Good First Issue Agent

> A read-only command-line agent that ranks open issues in a public GitHub repository (or a Sentry / GlitchTip project) by how approachable they look, explains every point of the score, and writes an investigation plan, with optional Gemini analysis through Google ADK.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: New contributors struggle to tell whether an issue is approachable, what is missing from its description, and where to start in an unfamiliar codebase. Labels alone are not enough; they are often missing, stale, or inconsistent.
- **Intended Users**:
  - Developers looking for a first open-source contribution (GitHub mode, no account or token needed).
  - Maintainers and teams who want to find well-scoped production errors for new team members to learn on (Sentry / GlitchTip mode).

### Key Features
- **Real data only**: fetches open issues from the GitHub REST API (pull requests are excluded) or unresolved issues from Sentry / GlitchTip.
- **Explainable ranking**: a deterministic 0–100 score where every point is shown with its reason (labels, clarity, reproduction steps, scope, vagueness, complexity, assignment, staleness).
- **Investigation plan**: next steps, files mentioned in the issue or stack trace, and open questions, without any AI.
- **Optional AI analysis (`--ai`)**: a Google ADK agent on Gemini explains the ranking and writes a detailed plan, using only read-only tools.
- **Guardrails in code, not just in the prompt**: tool allowlist, budgets, argument checks, secret / personal-data masking, prompt-injection flags, and verification of the model's answer against fetched evidence (see [Security & Privacy](#security--privacy-considerations)).
- **Text or JSON output** (`--format json`).
- **Chat in the ADK Web UI** (`adk web adk_web`): ask in plain language, the agent calls the same read-only tools with the same guardrails.
- **Strictly read-only**: no comments, labels, branches, commits, or pull requests are ever created.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+ (tested on Python 3.13, macOS)
- **Agent Framework**: Google Agent Development Kit (`google-adk==2.13.0`, `google-genai 2.33.0`)
- **Models**: Gemini, default `gemini-flash-latest` (configurable with `GEMINI_MODEL` or `--model`)
- **External APIs**: GitHub REST API (`api.github.com`), Sentry API (`/api/0/`), GlitchTip (Sentry-compatible API)
- **Libraries**: `requests`, `python-dotenv`, `truststore`; tests use `pytest`

---

## Architecture & Data Flow

```
            CLI (argparse)                    cli.py
                 |
     +-----------+------------+
     |                        |
 GitHub client          Sentry/GlitchTip client       github_client.py / sentry_client.py
 (GET only, timeouts,   (GET only, token required,     -> shared http_client.py
  max 3 pages,           same-host pagination,
  PRs removed)           PII masked on ingest)
     |                        |
     +-----------+------------+
                 |  normalized Issue objects            models.py
                 v
        Deterministic scorer  ---- reasons, uncertainties,  scoring.py
                 |                 next steps, evidence
                 v
     [optional --ai] Google ADK Agent (Gemini)             agent.py, prompts.py
        |- read-only tools bound to this repo/project
        |- before_tool / after_tool / before_model guardrail callbacks   guardrails.py
        '- answer checked against evidence ([unverified] markers)
                 |
                 v
        Text / JSON output (control characters stripped)   output.py
```

If the AI layer is not configured or fails, the deterministic results are still printed with a warning.

| Module | Responsibility |
| :--- | :--- |
| `cli.py` | Arguments, validation, orchestration, exit codes |
| `github_client.py` | GitHub repository, issues, comments, directory listing, file reading |
| `sentry_client.py` | Sentry / GlitchTip issues and latest-event stack traces |
| `http_client.py` | GET with timeout, one retry for network / 5xx errors, error mapping |
| `scoring.py` | Deterministic scoring rules and investigation steps |
| `guardrails.py` | Masking, truncation, injection detection, output verification, path checks |
| `agent.py` / `prompts.py` | Optional ADK agent, tools, callbacks, prompts |
| `output.py` | Terminal and JSON rendering |
| `web_agent.py` | Conversational agent for the ADK Web UI, with per-conversation guardrails |
| `adk_web/good_first_issue/agent.py` | Entry point that `adk web` loads (`root_agent`) |

---

## Prerequisites

- Python **3.11 or newer** (required by `google-adk`; tested with 3.13)
- `pip`
- Optional: a GitHub token (higher rate limit), a Gemini API key (`--ai`), a Sentry or GlitchTip auth token (error-tracker mode)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/good-first-issue-agent
   ```

2. **Create a virtual environment and install dependencies:**
   ```bash
   python3 -m venv .venv
   # Linux/macOS:
   source .venv/bin/activate
   # Windows (PowerShell):
   .venv\Scripts\Activate.ps1

   pip install -r requirements.txt        # to run the tool
   pip install -r requirements-dev.txt    # to also run the tests
   ```

3. **Configure environment variables (optional):**
   ```bash
   cp .env.example .env
   ```
   Nothing is required for public GitHub repositories. The `.env` file in this folder is loaded automatically; variables already set in your shell take precedence.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GITHUB_TOKEN` | No | *None* | Raises the GitHub API limit from 60 to 5,000 requests/hour. Read-only access is enough. |
| `GOOGLE_API_KEY` | Only for `--ai` | *None* | Gemini API key from Google AI Studio. `GEMINI_API_KEY` also works. |
| `GEMINI_MODEL` | No | `gemini-flash-latest` | Gemini model used by `--ai`. |
| `SENTRY_AUTH_TOKEN` | For `--source sentry` | *None* | Sentry token with `event:read` (and `project:read`). |
| `SENTRY_ORG` / `SENTRY_PROJECT` | For `--source sentry` | *None* | Organization and project slugs (or `--org` / `--project`). |
| `SENTRY_URL` | No | `https://sentry.io` | For self-hosted Sentry or another region. |
| `GLITCHTIP_AUTH_TOKEN` | For `--source glitchtip` | *None* | GlitchTip token (Profile → Auth Tokens) with `event:read`. |
| `GLITCHTIP_ORG` / `GLITCHTIP_PROJECT` | For `--source glitchtip` | *None* | Organization and project slugs. |
| `GLITCHTIP_URL` | No | `https://app.glitchtip.com` | Your GlitchTip instance (or `--base-url`). |
| `REQUESTS_CA_BUNDLE` | No | *None* | Custom CA file, only if HTTPS verification fails behind a proxy. |

> **Costs and quotas**: `--ai` sends issue text to the Gemini API. Usage may be billed or limited by your Google AI Studio / Google Cloud quota. Each `--ai` run makes at most 8 model calls and 6 tool calls per attempt, and at most two attempts (the second on `gemini-flash-lite-latest` if the first model is overloaded). A run usually takes 10–70 seconds. Without `--ai`, no model is called.

Tokens and keys are only read from the environment, never from command-line arguments, and are never printed or logged.

---

## How to Run

```bash
# Rank open issues in a public repository
python -m good_first_issue_agent --repo pallets/flask

# Only issues with a label, fetch fewer, show the top 3
python -m good_first_issue_agent --repo owner/repo --label "good first issue" --limit 10 --top 3

# Detailed plan for one issue (number or full issue URL)
python -m good_first_issue_agent --repo owner/repo --issue 123
python -m good_first_issue_agent --repo https://github.com/owner/repo/issues/123

# Machine-readable output
python -m good_first_issue_agent --repo owner/repo --format json

# Add Gemini analysis (needs GOOGLE_API_KEY)
python -m good_first_issue_agent --repo owner/repo --issue 123 --ai

# Sentry or GlitchTip (needs an auth token)
python -m good_first_issue_agent --source sentry --org my-org --project web-app
python -m good_first_issue_agent --source glitchtip --base-url https://glitchtip.example.com --org acme --project api
# AI on error-tracker data needs an explicit opt-in, because the data is private:
python -m good_first_issue_agent --source sentry --org my-org --project web-app --ai --allow-private-data-to-ai
```

### Chat in the ADK Web UI

```bash
adk web adk_web        # from agents/good-first-issue-agent, with the virtual environment active
```

Open http://127.0.0.1:8000, choose **good_first_issue**, and ask, for example: *"Find me an approachable issue in pandas-dev/pandas"*, then *"Plan #44957 for me"*. It needs `GOOGLE_API_KEY`. If the default model is busy, start it with `GEMINI_MODEL=gemini-flash-lite-latest adk web adk_web`. The web server is ADK's local development server: it has no login, so do not expose it to a network. A real conversation is in [`examples/adk-web-chat.txt`](examples/adk-web-chat.txt).

Run `python -m good_first_issue_agent --help` for all options. Limits: `--limit` 1–50 (default 20), `--top` 1–50 (default 5), `--timeout` 1–60 seconds (default 10).

**Exit codes**: `0` success (including "no issues found"), `1` network / API / rate-limit error, `2` invalid input.

---

## Example Input & Output

All output below is from real runs on 2026-10-24 (Python 3.13, macOS, with `GITHUB_TOKEN` and `GOOGLE_API_KEY` set). GitHub data changes, so your results will differ. The full log, including JSON output, is in [`examples/sample-output.txt`](examples/sample-output.txt).

### Ranking a busy repository

Of the 98 most recently updated open items read from pandas, 78 were pull requests and were excluded. Issues labelled `Needs Tests` (the bug is fixed and only a test is missing) rank highest. An assigned issue is pushed down.

```
$ python -m good_first_issue_agent --repo pandas-dev/pandas --limit 20 --top 3
Good First Issue Agent - pandas-dev/pandas (GitHub)
https://github.com/pandas-dev/pandas
Fetched 20 open issue(s), excluded 78 pull request(s). Showing top 3.

 1. [ 45/100] #44957  BUG: resampling with origin='end_day' raises ValueError: Values falls before first bin
      https://github.com/pandas-dev/pandas/issues/44957
      labels: Bug, Resample, Needs Tests | comments: 5
      + 8 actionable: Description states expected behaviour.
      +12 reproducible: Includes reproduction steps, code or error output.
      +10 limited scope: Looks small: label 'Needs Tests'; mentions 'docs', 'error message'.

 2. [ 45/100] #43941  BUG: Series.plot.hist segfault for timedelta64
      https://github.com/pandas-dev/pandas/issues/43941
      labels: Bug, Visualization, Needs Tests, Segfault | comments: 9
      + 8 actionable: Description states expected behaviour.
      +12 reproducible: Includes reproduction steps, code or error output.
      +15 limited scope: Looks small: label 'Needs Tests'; points to 1 specific file(s).
      - 5 possible complexity: Mentions 'Segfault' (inferred from wording).

 3. [ 35/100] #58866  BUG: pandas.read_json casts float column to int
      https://github.com/pandas-dev/pandas/issues/58866
      labels: Bug, Docs, IO JSON, Arrow | assigned: VashuTheGreat | comments: 14
      + 8 actionable: Description states expected behaviour.
      +12 reproducible: Includes reproduction steps, code or error output.
      +10 limited scope: Looks small: label 'Docs'.
      -10 already assigned: Assigned to VashuTheGreat.

Investigation plan for #44957 (top-ranked issue, deterministic)
  1. Read CONTRIBUTING.md, then comment on the issue to say you would like to work on it.
  2. Read all 5 comment(s): decisions may have changed since the issue was opened.
  3. Reproduce the problem locally using the steps in the issue before changing code.
  4. The issue's code or traceback mentions IPython/core/interactiveshell.py, pandas/core/frame.py,
    pandas/core/generic.py, pandas/core/resample.py. Some may be library files; find the ones that
    belong to this project and start there.
  5. Find the existing tests closest to the change and add or update one with your fix.
  Files found in the issue text: IPython/core/interactiveshell.py, pandas/core/frame.py,
    pandas/core/generic.py, pandas/core/resample.py, pandas/_libs/lib.pyx

Note: scores are heuristics from labels and issue text, not a guarantee of difficulty. Nothing was changed on GitHub or the error tracker; this tool is read-only.
[exit code 0]
```

### A beginner label is a signal, not proof

This issue has `good first issue` (+25), but it is already assigned and has 19 comments, so the plan tells you to ask first.

```
$ python -m good_first_issue_agent --repo pytest-dev/pytest --label 'good first issue'
Good First Issue Agent - pytest-dev/pytest (GitHub)
https://github.com/pytest-dev/pytest
Fetched 1 open issue(s), excluded 0 pull request(s). Showing top 1.

 1. [ 34/100] #14853  Expose FixtureFunctionDefinition as part of the public API
      https://github.com/pytest-dev/pytest/issues/14853
      labels: good first issue, topic: fixtures | assigned: teddygood | comments: 19
      +25 beginner label: Labelled 'good first issue' by the project (a signal, not proof).
      + 4 reproducible: Includes code or error output.
      -10 already assigned: Assigned to teddygood.

Investigation plan for #14853 (top-ranked issue, deterministic)
  1. Ask on the issue whether the assignee is still working on it before you start.
  2. Read all 19 comment(s): decisions may have changed since the issue was opened.
  3. Ask maintainers to confirm the expected behaviour or acceptance criteria.
  4. Code location is unknown. Search the repository for keywords from the title, e.g. `Expose
    FixtureFunctionDefinition part`.
  5. Find the existing tests closest to the change and add or update one with your fix.
  Open questions / uncertainty:
    - Someone is assigned: ask before starting work.

Note: scores are heuristics from labels and issue text, not a guarantee of difficulty. Nothing was changed on GitHub or the error tracker; this tool is read-only.
[exit code 0]
```

### Failure handling

```
$ python -m good_first_issue_agent --repo pandas-dev/pandas --label 'good first issue'
Good First Issue Agent - pandas-dev/pandas (GitHub)
https://github.com/pandas-dev/pandas

No candidate issues found.

Warnings:
  - No open issues with label(s) good first issue were found in the most recent 3 page(s) of
    results. Label names must match exactly; try without --label.

Note: scores are heuristics from labels and issue text, not a guarantee of difficulty. Nothing was changed on GitHub or the error tracker; this tool is read-only.
[exit code 0]

$ python -m good_first_issue_agent --repo pallets/flask --issue 5918
Error: #5918 in pallets/flask is a pull request, not an issue.
[exit code 2]

$ python -m good_first_issue_agent --repo pallets/this-repo-does-not-exist-xyz
Error: Repository pallets/this-repo-does-not-exist-xyz was not found. Check the spelling.
[exit code 1]

$ python -m good_first_issue_agent --repo 'not a repo'
Error: 'not a repo' is not a repository. Use the form owner/repo, e.g. pallets/flask.
[exit code 2]

$ python -m good_first_issue_agent --repo gitlab.com/foo/bar
Error: Only github.com repositories are supported (got 'gitlab.com').
[exit code 2]
```

When the shared unauthenticated GitHub limit (60 requests/hour per IP address) was used up, before a token was set:

```
$ python -m good_first_issue_agent --repo pallets/flask
Error: GitHub rate limit reached. The limit resets at 07:40 UTC. Setting GITHUB_TOKEN raises the limit from 60 to 5,000 requests/hour.
[exit code 1]
```

### AI-assisted output (`--ai`)

A live run with Gemini on the same day. `gemini-flash-latest` was overloaded (Google returned 503/504), so the agent switched to `gemini-flash-lite-latest` by itself and said so. The AI section is clearly separated from the deterministic plan. Files it names were checked against the issue text and tool results; any it could not verify would be marked `[unverified]`.

```
$ python -m good_first_issue_agent --repo https://github.com/pandas-dev/pandas/issues/44957 --ai
Good First Issue Agent - pandas-dev/pandas (GitHub)
https://github.com/pandas-dev/pandas

 1. [ 45/100] #44957  BUG: resampling with origin='end_day' raises ValueError: Values falls before first bin
      https://github.com/pandas-dev/pandas/issues/44957
      labels: Bug, Resample, Needs Tests | comments: 5
      + 8 actionable: Description states expected behaviour.
      +12 reproducible: Includes reproduction steps, code or error output.
      +10 limited scope: Looks small: label 'Needs Tests'; mentions 'docs', 'error message'.

Investigation plan for #44957 (selected issue, deterministic)
  1. Read CONTRIBUTING.md, then comment on the issue to say you would like to work on it.
  2. Read all 5 comment(s): decisions may have changed since the issue was opened.
  3. Reproduce the problem locally using the steps in the issue before changing code.
  4. The issue's code or traceback mentions IPython/core/interactiveshell.py, pandas/core/frame.py,
    pandas/core/generic.py, pandas/core/resample.py. Some may be library files; find the ones that
    belong to this project and start there.
  5. Find the existing tests closest to the change and add or update one with your fix.
  Files found in the issue text: IPython/core/interactiveshell.py, pandas/core/frame.py,
    pandas/core/generic.py, pandas/core/resample.py, pandas/_libs/lib.pyx

AI analysis (gemini-flash-lite-latest) - model-generated recommendation, verify before acting
------------------------------------------------------------
Summary: Issue #44957 reports a `ValueError: Values falls before first bin` when using `df.resample(rule='7d', origin='end_day')` because `end_day` sets `closed='right'` and `label='right'` by default, causing index values to fall outside the generated time bins range.

Why it may be approachable:
- Clear reproduction snippet provided in the issue description (#44957).
- Additional discussion and analysis in the comments clarifying how `origin='end_day'` sets default `closed`/`label` parameters and interacts with bin generation.
- Limited scope confined to time resampling and binner/bin generation logic.

Missing information / questions to ask maintainers:
- Should `origin='end_day'` adjust the start/first bin automatically to include all values in the index when `closed='right'` / `label='right'`, or should it raise an informative error?

Investigation plan:
1. Run the reproducible example from issue #44957 locally in python to inspect the exact traceback and behavior of `generate_bins_dt64`.
2. Examine `pandas/core/resample.py` where `origin='end_day'` is handled and default `closed`/`label` parameters are assigned.
3. Investigate `pandas/_libs/lib.pyx` (`generate_bins_dt64`) to see how bin boundaries and value checks are computed.
4. Write a unit test replicating the bug to verify any proposed fix or documentation update.

Where to look:
- `pandas/core/resample.py`
- `pandas/_libs/lib.pyx`
- `pandas/tests/resample/` (for existing resample tests)

Risks:
- Changing how bins are generated for `origin='end_day'` or `closed='right'` could affect backwards compatibility with existing pandas resample behavior across various rules and timezones.
------------------------------------------------------------
  ! gemini-flash-latest was overloaded or too slow; this answer comes from gemini-flash-lite-latest.

Note: scores are heuristics from labels and issue text, not a guarantee of difficulty. Nothing was changed on GitHub or the error tracker; this tool is read-only.
[exit code 0]
```

---

## How Ranking Works

Each issue starts at **15** points. Signals add or remove points, and the result is kept between 0 and 100. Related signals are grouped so the same evidence is not counted twice.

Wording-based signals ignore code blocks, URLs, traceback lines and issue-template confirmations such as `- [x] I have checked that this issue has not already been reported`. This was added after real pandas issues were inflated by their template. Files that appear only in tracebacks are still listed as evidence, but the plan warns that some may be library files.

**GitHub issues**

| Signal | Points | Evidence used |
| :--- | :--- | :--- |
| Beginner label | +25 | `good first issue`, `beginner`, `easy`, `first-timers-only`, … (case-insensitive) |
| Help-wanted label | +10 | `help wanted`, `up-for-grabs`, `hacktoberfest`, … |
| Actionable description | 0 to +20 | Expected behaviour, acceptance criteria / checklist, proposed solution |
| Reproduction steps | 0 to +15 | "Steps to reproduce", code blocks or tracebacks, numbered steps |
| Limited scope | 0 to +15 | Docs/typo/`needs tests` labels or wording, 1–3 specific files mentioned in the prose |
| Missing context | 0 to −20 | Empty body (−20), very short body (−12), no criteria or steps (−6) |
| Possible complexity | 0 to −15 | Words like refactor, migration, race condition, segfault; labels like `epic`, `rfc`, `needs discussion` |
| Not triaged | −5 | `needs triage` and similar: maintainers have not confirmed the issue yet |
| Already assigned | −10 | Someone is assigned |
| Blocked | −15 | `blocked`, `wontfix`, `duplicate`, `invalid`, … |
| Locked / long discussion / stale | −10 / −5 / −5 | Locked conversation, more than 20 comments, no activity for a year |

**Sentry / GlitchTip issues** use: known in-app file location (+15) or third-party code only (−10); specific error message (+15) or generic message such as "Script error." (−15); error types that are often local fixes, e.g. `KeyError`, `TypeError` (+10); timeouts, deadlocks or memory errors (−10); `fatal` level (−10) or `warning`/`info` (+5); high impact, 100+ users or 10,000+ events (−10), or low impact (+5); already assigned (−10).

**What the score does not guarantee**: it is a heuristic based on labels and wording. It cannot know the real size of a change, whether a maintainer still wants it, or whether someone is already working on it without being assigned. Use it to shortlist, then read the issue and ask the maintainers.

---

## How to Test

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests do not use the network or a real model. HTTP is replaced by a fake session, and the agent tests run the real `google-adk` runner with a scripted fake model. They cover:

- Repository-name parsing (URLs, `.git`, issue URLs, SSH form) and rejection of malformed input
- Pull-request exclusion, bounded pagination, label filters, empty bodies
- 404, 401, 403, rate limits (403 and 429), 410, 5xx with retry, timeouts, TLS failures, invalid JSON, and tokens never echoed in errors
- Sentry vs GlitchTip endpoints, same-host-only pagination, personal-data masking, stack-trace parsing
- Scoring rules, label variants, clamping, no double counting, prompt-injection flags
- Guardrails: secret masking, injection detection, output verification, path traversal
- Agent: tool allowlist, candidate-only issue access, `.env` and `..` refusal, tool and model budgets, timeouts, quota errors, empty answers, missing key
- CLI: `--help` as a module, option validation, JSON output, AI fallback, opt-in for AI on error-tracker data, terminal escape sequences stripped
- ADK Web agent: repositories only from the user's own messages (not from issue text), comments only for fetched issues, `.env` and `..` refused, per-message tool budget, answer verification, and that `adk web` can load `root_agent`

---

## Known Limitations

- **Heuristic scores**: keyword rules can be fooled by unusual wording; labels differ between projects.
- **Sampling**: only the most recently updated open issues are read (at most 3 pages; `--limit` up to 50). Very large repositories are sampled, not scanned.
- **GitHub rate limit**: 60 requests/hour without a token, shared by everyone on the same IP address (e.g. at an event). A normal run uses 2 requests; set `GITHUB_TOKEN` if you hit the limit.
- **Label filter**: GitHub requires every `--label` to match exactly (all labels must be present).
- **AI output can be wrong**: answers are checked for unknown issue numbers and file paths, but explanations may still be inaccurate. Treat them as suggestions.
- **Gemini availability**: during testing `gemini-flash-latest` was often overloaded (503/504). The agent then retries once with `gemini-flash-lite-latest`; if both fail, deterministic results are shown. `gemini-2.5-flash` returned "no longer available to new users" for a new key, so older tutorials may not work.
- **AI output checks cover file paths only**: issue numbers and file names are verified against fetched evidence, but directory names (e.g. `tests/resample/`) and function names are not.
- **Model name**: `gemini-flash-latest` is an alias that can change over time; set `GEMINI_MODEL` to pin a specific model.
- **Sentry / GlitchTip**: tested only with mocked API responses (based on the official Sentry docs and the GlitchTip source code); not yet run against a live instance. Sentry results default to the last 14 days.
- **Python 3.11+** is required because of `google-adk`. Tested on macOS; Linux and Windows are untested.
- No caching between runs and no conversation memory.

---

## Security & Privacy Considerations

- **Read-only**: only HTTP `GET` requests are made. The agent has no write tools, no shell, and no code execution.
- **Secrets handling**: tokens and keys come from environment variables / `.env` only. They are never passed as arguments, printed, or logged; error messages are masked as a last line of defence. Sentry/GlitchTip pagination only follows links to the configured host, so the token cannot be sent elsewhere, and tokens are refused over plain `http` except for `localhost`.
- **Untrusted input**: issue titles, bodies, comments, files and stack traces are treated as data. They are wrapped in `<untrusted_data>` blocks, and phrases that try to instruct an AI (e.g. "ignore previous instructions") are flagged in the output, not followed. Control characters are stripped before printing, so a malicious title cannot inject terminal escape codes.
- **Agent guardrails (enforced in code)**:
  - Only the listed read-only tools can run, and they are bound to the target repository/project.
  - Tools may only be used on issues that were fetched as candidates.
  - File paths must be relative, without `..`; `.env`, keys and credential files are refused.
  - At most 6 tool calls and 8 model calls per attempt, 40 seconds per Gemini request, 60 seconds per attempt, at most two attempts, and an output-length cap.
  - Tool results are masked for secrets and personal data before the model sees them.
  - The final answer is masked again; issue numbers and file paths not found in the fetched evidence are marked `[unverified]` and listed as warnings.
- **ADK Web UI guardrails**: a tool may only use a repository that the user wrote in the conversation. A repository named only inside issue text, comments or files is refused, so injected text cannot redirect the agent. The other rules are the same as in the CLI. Error trackers are not offered in the web UI because their data is private. `adk web` stores chat history locally in `adk_web/good_first_issue/.adk/`, which is git-ignored.
- **Data privacy**: in GitHub mode only public issue data (and, with `--ai`, the selected issue's text) leaves your machine. Error-tracker data is private: emails, IP addresses and secret-like values are masked when fetched; local variables, request data, user data and breadcrumbs are never read; and `--ai` requires `--allow-private-data-to-ai` before anything is sent to Gemini.
- **TLS**: certificates are verified with the operating system's trust store (`truststore`), so the tool works behind inspecting proxies without turning verification off.

---

## Future Improvements

- [ ] Use the repository tree to suggest likely files when an issue mentions none.
- [ ] Optional caching of API responses between runs.
- [ ] More sources (GitLab issues, Jira, Linear) behind the same scoring interface.
- [ ] Learn label conventions per repository (e.g. `E-easy` in Rust projects) from its label list.

---

## License

*This project is contributed under the repository's open-source license (MIT).*
