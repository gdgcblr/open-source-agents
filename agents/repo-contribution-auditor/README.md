# repo-contribution-auditor

> A CLI that audits a project folder against the [gdgcblr/open-source-agents](https://github.com/gdgcblr/open-source-agents) contribution criteria and emits deterministic findings as JSON and Markdown with a non-zero exit code on high-severity issues.

---

## Overview

### Problem Statement & Intended Users

- **Problem**: Contributors submitting to `gdgcblr/open-source-agents` frequently miss required README sections, forget lockfiles, accidentally track `.env` files, or leave secrets and template placeholders in their code. Manual review is slow and inconsistent.
- **Intended Users**: Contributors preparing a pull request to `gdgcblr/open-source-agents`, CI pipelines enforcing submission standards, and open-source maintainers reviewing incoming contributions.

### Key Features

- **7 deterministic checks** (README completeness, manifest + lockfile, env-example, secret scan, gitignore, folder naming, git scope) — all reproducible without an API key.
- **Secret scan with guaranteed redaction**: raw secret values are never stored or printed; only redacted pattern evidence is emitted.
- **Optional AI explanations** (`--explain`): sends only redacted finding JSON (no file contents) to Gemini and validates model output against a strict schema before merging.
- **Hard security guardrails**: no shell execution, symlink rejection, path containment, file/size/depth limits, HTML-escaped output.
- **Dual output**: JSON (machine-readable, CI-friendly) and Markdown (human-readable).

---

## Technical Stack

- **Language & Runtime**: TypeScript 5.7 / Node.js 25.1.0 (tested on Windows only; Linux/macOS not run)
- **Agent Framework / Core Library**: Vanilla Node.js script (no framework)
- **Models**: Gemini 2.0 Flash (optional, `--explain` mode only). Auth via `x-goog-api-key` header per official REST docs. **NOT verified against the live Gemini API** in this session.
- **External APIs / Tools**: Gemini REST API (optional, opt-in only), `dotenv` for env loading, `tsx` for dev/test execution

---

## Architecture & Data Flow

```
[CLI args] ──► [cli.ts — argument parsing, consent gate]
                    │
                    ▼
              [auditor.ts — orchestrator]
                    │
          ┌─────────┴────────────┐
          ▼                      ▼
    [walker.ts]            [checks.ts]
    Walk files             R01 README
    (skip node_modules,    R02 Manifest
     .git, symlinks,       R03 Env example
     enforce limits)       R04 Secret scan
          │                R05 Gitignore
          └────────────────► R06 Folder name
                             R07 Scope (git diff)
                    │
                    ▼
          [aiProvider.ts] ◄── GEMINI_API_KEY (env)
          (--explain only)     Schema validation
          Mock | GeminiProvider  Drop unknown ids
                    │
                    ▼
           [formatter.ts]
           JSON + Markdown
           (HTML-escaped)
                    │
                    ▼
                [stdout]
          exit 0 = PASS, exit 1 = FAIL (HIGH findings)
```

---

## Prerequisites

- **Node.js**: 20.0.0 or later
- **npm**: 9.0.0 or later (comes with Node.js)
- *(Optional)* A Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey) — only needed for `--explain` mode

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/repo-contribution-auditor
   ```

2. **Install dependencies:**
   ```bash
   npm ci
   ```

3. **Configure environment variables** *(optional — only for `--explain` mode)*:
   ```bash
   cp .env.example .env
   # Then edit .env and set GEMINI_API_KEY=your_key_here
   ```

4. **Build** *(optional — only needed for `node dist/cli.js`)*:
   ```bash
   npm run build
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | No | *None* | Gemini API key. Only required with `--explain --confirm-send`. Never logged, committed, or included in output. If absent, the tool uses the mock provider and no network calls are made. |

### Deterministic mode (no key needed)

```bash
npx tsx src/cli.ts path/to/your/agent --format json
```

No environment variable required. All checks run locally. No data leaves the machine.

### Live Gemini AI mode

```bash
# Step 1 — obtain a key: https://ai.google.dev/gemini-api/docs/api-key
export GEMINI_API_KEY="your-key-here"   # Linux/macOS
$env:GEMINI_API_KEY = "your-key-here"   # Windows PowerShell

# Step 2 — run with explicit consent flag
npx tsx src/cli.ts path/to/your/agent --explain --confirm-send
```

**What is sent to Gemini (per call):**
- Finding `id`, `severity`, `rule`, `description`, `file` (relative path), `line`, `evidence` (already redacted)
- Maximum 20 findings per call
- No file contents, no absolute paths, no environment variables, no source code

**Failure behavior:** If Gemini is unavailable, times out (30 s limit), returns an HTTP error, or returns malformed JSON, the tool logs an `AI-FALLBACK` info finding and returns deterministic results unchanged. Exit code is based on deterministic findings only.

**Auth:** API key is transmitted in the `x-goog-api-key` HTTP request header (official REST method). It is never placed in URLs, never logged, and the sanitiser strips it from error messages defensively.

**Live API status:** NOT VERIFIED against the live API in this session (2026-10-24). The HTTP client, request schema, response parsing, timeout (30 s), error handling, key sanitisation, and validation are implemented and verified with 14 HTTP mock tests. A valid `GEMINI_API_KEY` is required to verify live connectivity.

> **Privacy note:** Gemini API calls are subject to Google's [Generative AI Additional Terms of Service](https://ai.google.dev/terms). Review your key's data-retention and training settings before auditing confidential repositories.

---

## How to Run

```bash
# Audit a project folder (deterministic mode — no API key needed)
npx tsx src/cli.ts path/to/your/agent

# Audit with JSON output only
npx tsx src/cli.ts path/to/your/agent --format json

# Audit with Markdown output only
npx tsx src/cli.ts path/to/your/agent --format markdown

# AI explanations mode (requires GEMINI_API_KEY in .env or environment)
# --confirm-send acknowledges that redacted finding JSON will be sent to the API
npx tsx src/cli.ts path/to/your/agent --explain --confirm-send

# Custom git base ref for scope check
npx tsx src/cli.ts path/to/your/agent --base-ref upstream/main

# Show help
npx tsx src/cli.ts --help
```

After building (`npm run build`), you can also run:

```bash
node dist/cli.js path/to/your/agent
```

**Exit codes:**
- `0` — All checks pass (no HIGH severity findings)
- `1` — One or more HIGH severity findings
- `2` — Usage / argument error

---

## Example Input & Output

The following is **real output** from running the auditor against a synthetic project with known harmless issues (missing lockfile, leftover README placeholders, fake Google API key shape, incomplete `.gitignore`):

```bash
$ npx tsx src/cli.ts /tmp/rca-demo-project --format json
```

```json
{
  "targetDir": "/tmp/rca-demo-project",
  "timestamp": "2026-10-24T07:57:16.394Z",
  "truncated": false,
  "findings": [
    {
      "id": "F001", "severity": "medium", "label": "heuristic", "rule": "R01",
      "description": "README.md contains leftover template placeholder",
      "file": "README.md", "line": 1,
      "evidence": "Placeholder: \"[Project Name]\""
    },
    {
      "id": "F006", "severity": "medium", "label": "verified", "rule": "R02",
      "description": "package.json present but no lockfile found",
      "file": "package.json", "line": 0, "evidence": "lockfile missing"
    },
    {
      "id": "F007", "severity": "high", "label": "heuristic", "rule": "R04",
      "description": "Possible secret detected (google-api-key)",
      "file": "config.js", "line": 2,
      "evidence": "[REDACTED: Google API key shape AIza...BBBB]"
    },
    {
      "id": "F008", "severity": "medium", "label": "verified", "rule": "R05",
      "description": ".gitignore does not cover: venv/ or .venv/",
      "file": ".gitignore", "line": 0,
      "evidence": "Missing pattern for: venv/ or .venv/"
    },
    {
      "id": "F009", "severity": "info", "label": "heuristic", "rule": "R07",
      "description": "Scope check skipped: could not run git diff against \"origin/main\"",
      "file": "", "line": 0, "evidence": "git not available or base ref not found"
    }
  ],
  "annotations": []
}
```

**Exit code: `1`** (HIGH finding F007 = Google API key shape detected in `config.js`; evidence is always redacted).

*(Full 9-finding run omitted for brevity; findings F002–F005 are additional placeholder findings from the same README.)*

---

## How to Test

```bash
# Run the full test suite (61 tests, no API key required)
npm test

# Type-check without building
npx tsc --noEmit

# Build the project
npm run build

# Security audit of dependencies
npm audit

# Run the auditor against its own source tree (self-audit)
npx tsx src/cli.ts . --format markdown
```

Expected test output:
```
ℹ tests 61
ℹ pass 61
ℹ fail 0
```

The test suite includes:
- Walker, secret scanner, and all deterministic check rules (R01–R07)
- `validateModelOutput` schema validation (5 tests)
- MockProvider and GeminiProvider constructor tests
- **14 GeminiProvider HTTP mock tests** — including a test asserting the API key is absent from the fetch URL
- Security/injection regression tests

No live API calls are made during `npm test`. Gemini HTTP behavior is verified entirely through `globalThis.fetch` mocking.

---

## Known Limitations

- **Regex-based secret detection** is heuristic, not exhaustive. It catches common patterns (PEM keys, Google API key shape `AIza...`, AWS AKIA keys, GitHub `ghp_` tokens, high-entropy assignments ≥4.0 bits/char). It **will miss** uncommon formats, base64-encoded secrets, secrets in binary files, and split/obfuscated strings. It may also produce **false positives** on high-entropy non-secret strings.
- **README placeholder detection** uses regex string matching. Text inside fenced code blocks (` ``` ` fences) is intentionally excluded to avoid false positives — this is by design. Genuine unfilled placeholders in prose text are still detected.
- **Scope check (R07)** requires the target directory to be inside a git repository and the base ref to exist. If git is unavailable or the base ref is unknown, the check emits an `info` finding and continues rather than blocking.
- **AI explanations** are unverified suggestions. The model cannot change finding IDs, severities, or paths; its text is advisory only and may be hallucinated. AI is off by default.
- **Platform**: Tested on **Windows** (Node.js 25.1.0, npm 11.6.2) **only**. Linux/macOS not run in this session. A CI workflow template is provided in [`ci/github-actions.yml`](./ci/github-actions.yml) — it is an **inactive template** that has never had a workflow run. Copy it to `.github/workflows/` in your fork to activate.
- **Gemini adapter**: HTTP client, request/response schema, timeout (30 s), error handling, key sanitisation (header-based auth), and model-output validation are **implemented and verified with 14 HTTP mock tests**. Live connectivity against `generativelanguage.googleapis.com` is **NOT VERIFIED against the live API** — no `GEMINI_API_KEY` was available in this session. The mock provider is the safe default when no key is configured.
- **Secret-scan coverage**: All source files including `*.test.ts` are scanned. Test fixtures must use runtime string concatenation for any secret-like patterns. Regex detection is heuristic and will miss secrets encoded in unusual formats (base64, binary, obfuscated strings).

---

## Security & Privacy Considerations

- **Secrets Handling**: All secret evidence is redacted at detection time. The raw secret value never reaches the findings array, the JSON output, or the Markdown output. Pattern evidence is formatted as `[REDACTED: <pattern name>]`.
- **Data Privacy**: In deterministic mode (default), no data leaves the machine. In `--explain` mode, only the redacted findings JSON is sent to the Gemini API via the `x-goog-api-key` header — no file contents, no absolute paths, no source code.
- **Consent Gate**: `--explain` requires `--confirm-send` on the same command line. The tool prints what will be sent before any network call is made.
- **No shell execution**: The walker and all checks use Node.js `fs` APIs. The only subprocess invocation is `execFile("git", [...], { shell: false })` in R07, with a fixed argument list and no user-controlled interpolation.
- **Path containment**: `lstatSync` rejects symlinked target directories at the auditor entry point. The walker skips all symlinks during traversal via `lstatSync` on each entry.
- **Model cannot change verdicts**: The AI provider interface has no tools. Model output is validated against `{ annotations: [{ findingId, text }] }`. Unknown finding IDs are dropped; text is capped at 400 characters.
- **Output escaping**: All file-derived strings and model text are HTML-escaped before appearing in Markdown output, preventing `<script>` injection in downstream renderers.

### Guardrails: Code-enforced vs Model-instruction

| Control | How enforced |
| :--- | :--- |
| Key not in URL | Code: `x-goog-api-key` header only; never string-interpolated into URL |
| Key not in errors | Code: sanitiser regex strips `x-goog-api-key` header value from thrown errors |
| No file contents sent | Code: `buildGeminiPayload` projects only 7 safe fields; no `content` field |
| Unknown finding IDs dropped | Code: `validateModelOutput` checks every ID against input set |
| AI cannot add findings | Code: only `annotations` array accepted; any extra keys ignored |
| AI text capped at 400 chars | Code: `text.substring(0, 400)` |
| No shell execution | Code: `execFile(..., { shell: false })` |
| Model instructed not to invent | Prompt text only — **not** code-enforced; model may still hallucinate |

### Threat Model Summary

| Threat | Mitigation |
| :--- | :--- |
| Secret leaked in output | Scanner redacts before storing; evidence strings never contain raw values |
| Path traversal via target dir | `realpath` + strict prefix check; symlinks rejected |
| Prompt injection via README | Deterministic checks are code-only; AI annotations cannot change finding IDs/severities |
| Model returns invented findings | Schema validation drops any `findingId` not in the original set |
| Shell injection via file names | No shell; `execFile` with fixed args; user input never interpolated |
| XSS in Markdown output | All external strings HTML-escaped before rendering |

---

## Future Improvements

- [ ] Respect `.gitignore` patterns during walk (currently uses a static skip list).
- [ ] Support custom rule configuration via a `auditor.config.json` file.
- [ ] Add Python secret patterns (e.g., `sk-` OpenAI keys).
- [ ] GitHub Actions integration example.
- [ ] Stream findings as they are discovered rather than batching.

---

## License

*This project is contributed under the repository's open-source license (MIT).*
