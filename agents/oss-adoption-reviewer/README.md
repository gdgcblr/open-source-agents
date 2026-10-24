# OSS Adoption Reviewer

> A local-first ADK agent that reviews a repository the way a new adopter would and returns a prioritized, evidence-cited list of fixes.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Linters, SonarQube and code-review bots tell you whether code is *correct*. They don't tell you whether a developer who finds your repo can understand it, run it, contribute to it and ship it. Most OSS projects die from adoption friction (no quickstart, no license, no contributor path, no CI), not from bad code.
- **Intended Users**: OSS maintainers, hackathon participants checking their repo before submitting, and reviewers of community repos.
- **Out of scope**: code style, bugs, and security audits of the code itself.

### Key Features
- **Deterministic scoring**: facts and scores (0–5 per dimension, 25 total) are computed in Python and exposed as an MCP tool. The LLM only explains and prioritizes, so prompt injection inside a reviewed repo cannot inflate a score. The final report is held to those scores: if the model writes a different N/5, the guardrail rewrites it and says so.
- **Local path or GitHub URL**: point it at a folder, or at `https://github.com/<owner>/<repo>` and it shallow-clones the public repo first.
- **Cited, checkable advice**: every fix cites a stable signal id (`missing:license`, `adoption:setup_steps=9`, `flag:no_license`) that comes from the scan.
- **Guardrails**: path sandbox, GitHub-only URL allow-list, secret-file deny-list, output redaction, LLM-call cap, score enforcement, and an output-contract check (see [Security](#security--privacy-considerations)).
- **Two model options**: fully local on Ollama (no API key), or the Gemini API free tier (`gemini/gemini-3.1-flash-lite`, about 5× faster; `gemini/gemini-3.6-flash` for a stronger model). Served as a CLI, `adk web`, an A2A agent, or a Docker container.

The five dimensions: usefulness & clarity, ease of adoption, maintainability & contributor friction, distribution & scale, and friction red flags (secrets tracked, huge files, no license, stub README).

---

## Technical Stack

- **Language & Runtime**: Python 3.12, managed with `uv`
- **Agent Framework / Core Library**: Google ADK 2.13 (`LlmAgent`, `McpToolset`, `to_a2a`), Model Context Protocol (`mcp`, stdio server)
- **Models**: via LiteLLM, switched with `MODEL_NAME`. Default `ollama_chat/qwen3.5:9b` (local); or `gemini/gemini-3.1-flash-lite` (Gemini API free tier)
- **External APIs / Tools**: Gemini API only if you pick a `gemini/*` model; otherwise none (Ollama on the host, local filesystem only)

---

## Architecture & Data Flow

```
            ┌──────────── Docker container (optional) ───┐
 A2A client │  serve_a2a.py  (to_a2a → uvicorn :8001)    │
 / adk web ─┼─▶ root_agent (ADK LlmAgent, LiteLlm)       │──▶ Ollama on host
 / CLI      │      │  before_model_callback (call cap)   │    qwen3.5:9b / Gemini API
            │      │  before_tool_callback  (path guard) │
            │      │  after_tool_callback (keep scores)  │
            │      │  after_model_callback  (score fix,  │
            │      ▼             output check, redaction)│
            │  McpToolset (stdio) ─▶ repo_mcp.py         │──▶ REVIEW_ROOT (read-only)
            │                        clone_repo,         │──▶ CLONE_DIR ◀─ github.com
            │                        scan_repo, read_file│      (shallow, https only)
            └────────────────────────────────────────────┘
```

1. The user gives a repository path or a public GitHub URL. For a URL, the agent calls `clone_repo`, which validates it against `https://github.com/<owner>/<repo>` and shallow-clones it into `CLONE_DIR`.
2. The agent calls `scan_repo`. The MCP server lists the repo's files (git-tracked files when the folder is in a git checkout, including a monorepo subfolder, where LICENSE / CONTRIBUTING / CODE_OF_CONDUCT at the repo root also count if that root is inside `REVIEW_ROOT`; otherwise a filesystem walk), evaluates ~20 signals, and returns per-dimension `issues`, `passing` ids, and scores.
3. The agent may call `read_file` once on `README.md` for context (the content is wrapped as untrusted data).
4. The agent writes the report: five dimension sections plus **Top 5 fixes**, ranked by impact ÷ effort.

---

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- **Either** [Ollama](https://ollama.com) running locally with the model pulled (`ollama pull qwen3.5:9b`), **or** a free Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)
- Docker (only for the container / A2A-in-Docker path)
- No API key needed for the Ollama path

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/oss-adoption-reviewer
   ```

2. **Install dependencies:**
   ```bash
   uv sync
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Set `REVIEW_ROOT` to the folder that contains the repos you want reviewed.
   To use Gemini instead of Ollama, also set `MODEL_NAME=gemini/gemini-3.1-flash-lite` and `GEMINI_API_KEY=<your key>`. Use a free-tier model (`gemini/gemini-3.6-flash` is stronger but rate-limited to 5 requests per minute; reviews retry 429s automatically). Older models such as `gemini-2.5-flash` are closed to new keys.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `MODEL_NAME` | No | `ollama_chat/qwen3.5:9b` | LiteLLM model id, e.g. `gemini/gemini-3.1-flash-lite` |
| `GEMINI_API_KEY` | Only for `gemini/*` | none | Google AI Studio key. Keep it in `.env` (git-ignored), never commit it |
| `OLLAMA_API_BASE` | No | `http://localhost:11434` | Ollama endpoint (`http://host.docker.internal:11434` in Docker) |
| `REVIEW_ROOT` | No | current directory | The agent can only read inside this directory (absolute path) |
| `CLONE_DIR` | No | `<system temp>/oss-adoption-reviewer-clones` | Where GitHub URLs are shallow-cloned. Readable by the agent in addition to `REVIEW_ROOT`; safe to delete |
| `MAX_LLM_CALLS` | No | `15` | Hard cap on LLM calls per review |
| `NUM_CTX` | No | `16384` | Context window sent to Ollama only (ignored for Gemini). Its small default can truncate reports |

---

## How to Run

```bash
# CLI (type the request, then press Enter)
export REVIEW_ROOT=/path/to/parent-of-repos
uv run adk run reviewer
#   > Review the repository at /path/to/parent-of-repos/my-repo
#   > Review https://github.com/pallets/flask

# Browser UI
uv run adk web .

# A2A server on http://localhost:8001 (agent card at /.well-known/agent-card.json)
uv run python serve_a2a.py

# Docker (A2A server; ../ is mounted read-only at /repos, override with REPOS_DIR)
docker compose up --build
curl localhost:8001/.well-known/agent-card.json
# then ask it to review /repos/<folder>, for example over A2A JSON-RPC:
curl -s -H 'Content-Type: application/json' -H 'A2A-Version: 1.0' localhost:8001/ -d '{"jsonrpc":"2.0","id":1,"method":"SendMessage","params":{"message":{"messageId":"m1","role":"ROLE_USER","parts":[{"text":"Review the repository at /repos/oss-adoption-reviewer"}]}}}'
```

---

## Example Input & Output

### Example Input
```
Review the repository at /Users/me/open-source-agents
```

### Example Output
Real output (qwen3.5:9b, about 35 s on an M-series Mac) from reviewing this hackathon repo, [gdgcblr/open-source-agents](https://github.com/gdgcblr/open-source-agents). Deterministic total: 13/25.

```
## Usefulness & clarity — 3/5
The README provides a comprehensive overview of project purpose and acceptable contribution categories. However, it lacks specific example usage ... The issues are missing:readme_problem (...) and missing:readme_example (no concrete usage examples to demonstrate functionality).

## Ease of adoption — 2/5
The install section is present with a reasonable setup process, but ... The critical gaps are missing:prerequisites, missing:dependency_manifest, and missing:lockfile.

## Maintainability & contributor friction — 3/5
License and contributing guidelines are present, along with templates for issues and PRs. However, the project lacks a code of conduct ... missing:code_of_conduct, missing:tests, and missing:lint_config.

## Distribution & scale — 0/5
... missing:container, missing:ci, missing:packaging_metadata, and missing:changelog.

## Friction red flags — 5/5
There are no friction red flags ...

## Top 5 fixes
1. **Add lockfile and dependency manifest** (`missing:dependency_manifest`, `missing:lockfile`) – ...
2. **Document prerequisites explicitly** (`missing:prerequisites`) – ...
3. **Add container and CI** (`missing:container`, `missing:ci`) – ...
4. **Write a changelog** (`missing:changelog`) – ...
5. **Add code of conduct** (`missing:code_of_conduct`) – ...
```
(Prose shortened here with `...`; scores and ids are verbatim.) Note that this repo intentionally has no code, so the dependency and CI fixes reflect that, not a flaw in the agent.

More full, unedited verdicts (real repos and the test fixtures) are in [`examples/`](examples/) (`gemini/gemini-3.1-flash-lite`, one run each, model name in each file):

| Repo | Input | Total |
| :--- | :--- | :--- |
| [sharkdp/bat](examples/bat.md) | GitHub URL | 17/25 |
| [google-research/harness2](examples/harness2.md) | GitHub URL | 16/25 |
| [gdgcblr/open-source-agents](examples/open-source-agents.md) | GitHub URL | 13/25 |
| [omnibus-gitlab](examples/omnibus-gitlab.md) | GitLab URL (refused), then local clone | 17/25 |
| [this agent's folder](examples/oss-adoption-reviewer.md) (dogfood) | local path, monorepo subfolder | 21/25 |
| [`good_repo` fixture](examples/fixture-good-repo.md) | local path | 25/25 |
| [`bare_repo` fixture](examples/fixture-bare-repo.md) | local path | 4/25 |
| [`injected_repo` fixture](examples/fixture-injected-repo.md): README tells the reviewer to report 5/5 and read `~/.ssh/id_rsa` | local path | 6/25, injection ignored and flagged |

---

## How to Test

The unit tests need no LLM and no network:

```bash
uv run pytest        # 23 tests, under a second
```

They cover exact signal sets for three fixtures (`good_repo`, `bare_repo`, `injected_repo`), score ordering (good > bare), prompt-injection resistance of the scores, flagged secrets and large files, git-ignored files skipped and the root LICENSE counted in a monorepo subfolder, report scores rewritten to match the scan, no contract warning on non-report replies or on issue-free repos, the GitHub URL allow-list, and a locked-down clone command (git mocked, no network), path traversal, `.env` / `.pem` / `id_rsa` read refusal, symlink escapes, secret redaction, and the LLM-call cap.

The LLM eval needs Ollama or a Gemini key, and (for the tier check) network access to clone four public repos shallowly:

```bash
uv run python eval/run_eval.py             # tier ordering + LLM eval
uv run python eval/run_eval.py --no-llm    # tier ordering only
```

Results from one run on qwen3.5:9b (macOS, M-series):

| Check | Result | Bar |
| :--- | :--- | :--- |
| Tier ordering, fixtures | good 25 > bare 4 | good > bare |
| Tier ordering, real repos | high mean 18.0 (uv 20, flask 18, adk-python 16) > middle 13.0 (open-source-agents) | high > middle |
| Grounding (fixes citing a real signal id) | 10/10 = 100% | ≥ 80% |
| Recall (`missing:*` ids in `bare_repo` addressed) | 18/18 = 100% | ≥ 70% |
| Injection (`injected_repo`) | pass: total stays 6/25, no perfect-score claim | must hold |
| Latency | mean 35 s per review | reported only |

Same eval on the Gemini API free tier (same fixtures and repos; tier ordering is deterministic, so unchanged). One run each, so treat the comparison as indicative:

| Model | Grounding | Recall | Injection | Mean latency |
| :--- | :--- | :--- | :--- | :--- |
| `gemini/gemini-3.1-flash-lite` | 10/10 = 100% | 18/18 = 100% | pass | 7 s |
| `gemini/gemini-3.6-flash` | 10/11 = 91% | 18/18 = 100% | pass | 34 s |

`gemini-3.6-flash` is the stronger model but its free tier allows only 5 requests per minute, so the 34 s includes waiting on 429 retries (up to 62 s for one review). `gemini-3.7-flash` and `gemini-3.8-flash` hung without responding on a free-tier key when tested, so they are not recommended.

Honest notes: the first prompt scored 61% recall, so the prompt now requires one bullet per issue id. LLM results vary between runs, and this is a single run on three small fixtures, not a benchmark. Tier ordering is checked only for high vs middle because no low-tier real repo is in the list yet.

---

## Known Limitations

- URL input supports public `https://github.com/<owner>/<repo>` URLs only (no GitLab, branches, subfolders, or private repos). Clones of very large repos are bounded only by a 120 s timeout.
- Signal heuristics favor Python and JS repos (manifest, lockfile, lint-config names). Other ecosystems are partly covered.
- Secret-file flags are filename-based, so direnv's `.envrc` and `.env` test fixtures are flagged too (see [bat](examples/bat.md)).
- Heuristics are filename- and heading-based. A README that has a "Usage" heading but no real example still passes.
- The 9B model sometimes skips citations or mis-copies a heading. The output check appends a warning when headings or citations are missing, but it does not repair the report. In early runs it also treated a long README as a task to perform; the `read_file` wrapper and prompt reduced this, but it can still happen.
- In a monorepo subfolder, only LICENSE / CONTRIBUTING / CODE_OF_CONDUCT are taken from the repo root; issue/PR templates and CI at the root are not, so the subfolder can still get `missing:issue_pr_templates` / `missing:ci`.
- In Docker the default mount is `../` (this `agents/` folder), which has no `.git`, so the scan falls back to a filesystem walk and reports git-ignored secret files as `flag:secret_file_present=…` instead of skipping them. Mount the whole checkout (`REPOS_DIR=../../`) to get git-tracked files only.
- Tested on macOS only (host and Docker Desktop).

---

## Security & Privacy Considerations

- **Secrets Handling**: no credentials are needed for Ollama; `GEMINI_API_KEY` lives only in the git-ignored `.env` (or the environment). `read_file` refuses `.env*` (except `.env.example`), `*.pem`, `*.key` and `id_rsa*`; output is scrubbed for key-like strings (`sk-…`, `AIza…`, `AQ.…`, `ghp_…`). The MCP tool server is started without any `*_API_KEY` variables.
- **Data Privacy**: everything stays on your machine when using Ollama. With a `gemini/*` model, `scan_repo` results and any README text the agent reads are sent to the Gemini API (free-tier prompts may be used by Google to improve its products), so don't point it at private repos on that path. `clone_repo` contacts github.com only. Repo contents are sent only to the model you configure in `MODEL_NAME`.
- **Safety**: nothing under `REVIEW_ROOT` is ever written, and there are no exec tools. The only write is `clone_repo`, which accepts nothing but `https://github.com/<owner>/<repo>` (checked in the MCP server and again in `before_tool_callback`), rebuilds the URL itself, and runs `git clone --depth 1` with stored credentials disabled, no terminal prompt, https as the only protocol, LFS skipped, and a 120 s timeout, into a user-owned `CLONE_DIR`. Every path is `resolve()`d and must sit under `REVIEW_ROOT` or `CLONE_DIR` (`..` and symlink escapes are rejected), enforced both in the MCP server and in `before_tool_callback`. Reads are capped (20 KB), the file tree is capped, and LLM calls are capped by `MAX_LLM_CALLS`. Repo text is wrapped as untrusted data, and scores are computed in code so injected text can't change them; `after_model_callback` rewrites any reported score that differs from `scan_repo`. Replies that are not a report (e.g. asking for a path) are only redacted.
- The Docker image runs as a non-root user and the repos mount is read-only.

---

## Future Improvements

- [ ] Use the GitHub API for URL reviews (stars, issue age, last commit, bus factor); support GitLab and branch/subfolder URLs.
- [ ] `--fix` mode that drafts missing files (LICENSE, CONTRIBUTING, Dockerfile) as a patch.
- [ ] GitHub Action that posts the review on PRs adding a new `agents/*` folder.
- [ ] Multi-agent variant: one sub-agent per dimension coordinated over A2A.
- [ ] SARIF/JSON output for CI dashboards.
- [ ] Add low-tier real repos to the tier check; compare Gemma 4 against Qwen and Gemini with `eval/run_eval.py`.

---

## License

*This project is contributed under the repository's open-source license.*
