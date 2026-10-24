# Issue Reproduction Assistant

> Point it at a GitHub issue and get an evidence-backed reproduction brief: likely code locations with line-level evidence, missing information, reproduction steps, recent commit history, and (with a model) a draft failing test — via CLI, **MCP** server, or **A2A** agent.

---

## Overview

### Problem Statement & Intended Users

- **Problem**: Maintainers spend a large share of triage time on vague bug reports: Is it reproducible? Where in the code might it live? What should we ask the reporter? New contributors face the same cold start.
- **Intended Users**: Open-source maintainers, first-time contributors picking up an issue, and other agents/IDEs that need triage as a tool.

### Key Features

- **Live GitHub input**: `owner/repo#123` → issue + comments fetched, repository shallow-cloned read-only. Local issue files + local checkouts also supported.
- **Deterministic localization (no model needed)**: parses stack traces (JS/TS, Python, Go/Rust/Java-style), identifiers, error strings and versions; ranks repository files and returns matching lines, related existing tests, and recent git history.
- **Offline by default**: without `--allow-upload` nothing leaves the machine and no API key is required.
- **Model-assisted reports** (opt-in): structured JSON brief (summary, severity, likely areas, hypotheses, questions, steps, confirmation criteria, **draft failing test**). Paths proposed by the model are validated against the real repository; unusable output falls back to the evidence-only report.
- **Plug-and-play models**: `gemini` (Gemini free tier or higher-end models) and `ollama` (local Gemma or any Ollama model). New providers are one small adapter.
- **Three interfaces on one core**: CLI, MCP server (5 read-only tools), and an A2A agent (agent card + JSON-RPC `message/send`).
- **Safety**: never executes repository code; clone hooks disabled; secrets redacted/skipped; strict input validation.

## Technical Stack

- **Language & Runtime**: TypeScript, Node.js 20+
- **Protocols**: Model Context Protocol (`@modelcontextprotocol/sdk`), Agent2Agent (A2A, JSON-RPC over HTTP)
- **Models**: Gemini via `@google/genai` (default `gemini-3.8-flash`); local Gemma (default `gemma3`) via Ollama
- **External APIs / Tools**: GitHub REST API, `git`

## Architecture & Data Flow

```
 GitHub issue ──▶ fetch + redact ─┐
                                  ├─▶ signals (stack frames, identifiers, errors, versions)
 repo (clone or local) ──▶ scan ──┘          │
                                             ▼
                              localize + related tests + git history   ← deterministic evidence
                                             │
                      ┌──────────────────────┴──────────────────────┐
                      ▼ (no --allow-upload)                          ▼ (--allow-upload)
             evidence-only brief                       ModelProvider (Gemini | Ollama/Gemma | your adapter)
                                                                     │  validated JSON, hallucinated paths dropped
                                                                     ▼
                                                           Markdown brief (+ draft test)

 Interfaces:  CLI  ·  MCP stdio server (tools)  ·  A2A HTTP agent (agent card + message/send)
```

## Prerequisites

- Node.js 20+, npm, and `git` on your `PATH`
- Optional: `GEMINI_API_KEY` (model-assisted mode with Gemini) or a running [Ollama](https://ollama.com) with a model pulled (e.g. `ollama pull gemma3`)
- Optional: `GITHUB_TOKEN` to avoid GitHub's unauthenticated rate limit (60 requests/hour)

## Installation & Setup

```bash
cd agents/issue-reproduction-assistant
npm ci
cp .env.example .env     # only needed for model-assisted mode / tokens
```

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `AI_PROVIDER` | No | `gemini` | `gemini` or `ollama` |
| `AI_MODEL` | No | `gemini-3.8-flash` / `gemma3` | Model ID for the chosen provider; change without code changes |
| `GEMINI_API_KEY` | Only for `gemini` + `--allow-upload` | *None* | Gemini API key |
| `OLLAMA_HOST` | No | `http://localhost:11434` | Ollama server URL |
| `GITHUB_TOKEN` | No | *None* | Raises GitHub API rate limits; never logged |
| `A2A_PORT` | No | `4747` | A2A server port (binds to `127.0.0.1`) |
| `A2A_ALLOW_UPLOAD` | No | *unset* | Set to `1` to let A2A requests use the configured model |

## How to Run

### CLI

```bash
# Offline, evidence-only (no key, nothing leaves your machine except GitHub/git fetches)
npm start -- --github owner/repo#123

# Model-assisted with Gemini
AI_PROVIDER=gemini GEMINI_API_KEY=... npm start -- --github owner/repo#123 --allow-upload

# Fully local with Gemma via Ollama
AI_PROVIDER=ollama AI_MODEL=gemma3 npm start -- --github owner/repo#123 --allow-upload

# Local issue file + local checkout, JSON output
npm start -- --issue ./bug.md --repo ../my-project --json --out brief.json
```

### Browser-ready report (HTML)

```bash
npm start -- --github "Nerajno/learnt-project#43" --html          # writes reports/<issue>.html + .md
npm start -- --github "Nerajno/learnt-project#43" --html --open   # ...and opens it in your browser
```

The self-contained page (no scripts, escaped content, `reports/` is git-ignored) opens with **"Reproduce it from scratch"**: the exact `git clone` + commit checkout, install and start commands detected from the project (package manager, dev script, default URL), what to open and what to look for in DevTools for UI issues, followed by analysis, evidence and draft tests.

#### Worked UI example

[Nerajno/learnt-project#43](https://github.com/Nerajno/learnt-project/issues/43): every project screenshot 404s. The agent localizes `src/data/projects.ts` and generates the steps below; I followed them manually (clone, `npm ci`, `npm run dev`) and `curl` for `/images/screenshots/status-tracker.png` returned 404 on that commit.

### MCP server (stdio)

```bash
npm run mcp
```

Example client configuration (Claude Desktop / VS Code / any MCP client):

```json
{
  "mcpServers": {
    "issue-reproduction-assistant": {
      "command": "npm",
      "args": ["run", "--silent", "mcp"],
      "cwd": "/absolute/path/to/agents/issue-reproduction-assistant"
    }
  }
}
```

Tools (all read-only): `fetch_github_issue`, `extract_issue_signals`, `locate_code`, `file_history`, `investigate_issue` (offline unless `allowUpload: true`).

### A2A agent

```bash
npm run a2a          # offline mode; set A2A_ALLOW_UPLOAD=1 to enable the model
curl localhost:4747/.well-known/agent-card.json
curl -X POST localhost:4747/ -H 'content-type: application/json' -d '{
  "jsonrpc":"2.0","id":1,"method":"message/send",
  "params":{"message":{"role":"user","messageId":"m1",
    "parts":[{"kind":"text","text":"Please triage owner/repo#123"}]}}}'
```

The reply is an A2A `Message` with a Markdown `text` part and a structured `data` part (`mode`, `likelyAreas`, `questionsForReporter`).

## Example Input & Output

Real run (offline mode) against a public issue, [tahirhsn91/SchoolManagementSystem#12](https://github.com/tahirhsn91/SchoolManagementSystem/issues/12) (trimmed):

```bash
npm start -- --github "tahirhsn91/SchoolManagementSystem#12"
```

```markdown
# Issue reproduction brief

> Offline evidence-only mode: no model was used and no data left this machine.

## Likely areas
- `artifacts/api-server/src/routes/dashboard.ts` (medium) — path mentioned in the issue; references dashboard, teacherCount; file name matches "dashboard"
- `artifacts/api-server/src/routes/index.ts` (low) — references dashboard
- `lib/api-client-react/src/custom-fetch.ts` (low) — references TypeError

## Questions for the reporter
- What are the exact steps (or a minimal example) that trigger the problem?
- What did you expect to happen, and what happened instead?
```

Model-assisted run (`--allow-upload`, Gemini; trimmed from a real run, wording varies by model):

```markdown
## Summary
TypeError occurs on GET /api/dashboard when accessing 'count' on an undefined element of teacherCountRows.
**Estimated severity:** medium

## Likely areas
- `artifacts/api-server/src/routes/dashboard.ts` (high) — handles GET /api/dashboard and queries count rows for teachers, students, classrooms.

## Candidate tests
- GET /api/dashboard with an empty teachers table falls back to 0 without throwing.
```

## How to Test

```bash
npm test      # builds, then runs 17 tests with node:test
```

Tests use temporary git repositories, a mocked model provider and mocked `fetch`; no network, API key or Ollama is needed. They cover signal extraction, localization, git history, the LLM + fallback paths, provider configuration, Ollama request shape, an in-memory MCP client/server session, and the A2A HTTP endpoint.

## Known Limitations

- Localization is heuristic (lexical); it can miss code that the report doesn't name, and may rank generic matches. Treat results as leads.
- Draft tests and reproduction steps are unverified suggestions; nothing is executed.
- "From scratch" steps are detected for Node projects only (package.json); other ecosystems get a generic "see the README" step.
- Only the first 1,000 eligible text files ≤256 KB are scanned; large monorepos may be partly covered.
- Model-assisted output quality depends on the model; Gemini availability, model IDs and free-tier limits can change. The Gemini and Ollama adapters are covered by mocks and request-shape tests; Gemini was not exercised live in this repo's tests.
- A2A support is a minimal `message/send` implementation (no streaming, tasks, or push notifications).
- Tested on macOS with Node 24; other platforms untested. Windows may differ for path handling.

## Security & Privacy Considerations

- **Secrets**: Keys come from the environment/`.env` (git-ignored) and are never logged. Issue text, comments, and files are redacted for common key/token patterns; `.env`, key/credential-like files, hidden paths, symlinks, and vendor/build directories are skipped. Redaction is best-effort, not a guarantee.
- **Data privacy**: By default nothing is sent to a model. With `--allow-upload` (or MCP `allowUpload`, A2A `A2A_ALLOW_UPLOAD=1`), redacted issue text and selected excerpts go to the configured provider — Google for `gemini`; your own machine for `ollama`. Avoid private/regulated repositories with hosted models.
- **Safety**: The agent never runs repository code, tests, or shell commands from the issue. Clones use `git clone --depth 100` with hooks disabled, via argument arrays (no shell), for validated `owner/repo` names. File-history reads reject paths escaping the repository. Untrusted issue/repository text is delimited and the model is instructed not to follow embedded instructions (prompt injection can't be fully ruled out).
- **Network surface**: The A2A server binds to `127.0.0.1`, limits request size to 64 KB and concurrency to 2, and has no authentication; do not expose it publicly without a gateway. The MCP `repositoryPath` arguments let the connected client read source files from local directories you point it at.

## Adding a model provider

Implement `ModelProvider` (`src/model-provider.ts`) and register a factory in `src/config.ts`. The pipeline, MCP, and A2A layers need no changes.

## Future Improvements

- [ ] Wrap the pipeline as a Google ADK agent for multi-step planning.
- [ ] Optionally *run* a generated test in a sandbox/container to verify reproduction.
- [ ] Semantic (embedding) retrieval to complement lexical localization.
- [ ] A2A streaming/tasks and authentication.
- [ ] Post briefs back to the issue as a comment (with human approval).

## License

This project is contributed under the repository's MIT license.
