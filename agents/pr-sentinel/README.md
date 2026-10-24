# PR Sentinel

> Autonomous Multi-Agent Pull Request Review, Security Triage, and Auto-Patch System powered by Google Gemini.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Reviewing open-source pull requests is time-consuming, repetitive, and error-prone. Critical issues—such as leaked API tokens, unvalidated command execution, missing documentation templates, and broken repository guidelines—frequently slip past manual reviews or slow down maintainer velocity.
- **Intended Users**: Open-source maintainers, hackathon participants, code reviewers, and developer platform teams looking to automate PR triage, enforce quality standards, and receive instant corrective patches.

### Key Features
- **Multi-Agent Orchestrated Swarm**: Coordinates four specialized autonomous agents:
  - 🛡️ **SecuritySentinel**: Deep scanner for leaked API keys (Gemini, OpenAI, AWS, GitHub tokens), unsafe `eval`/`exec`, and shell command injections.
  - 📋 **ComplianceAuditor**: Audits contribution structure against `CONTRIBUTING.md` standards (directory isolation, kebab-case naming, manifest presence, README completeness).
  - 🏗️ **QualityCritic**: Inspects AST structures for error resilience, asynchronous error handling, modularity, and maintainability.
  - 🛠️ **PatchSynthesizer**: Synthesizes unified git diff patches ready for review or immediate application.
- **Dual Execution Engine (Zero-Key Demo + Live Gemini)**:
  - **Live Gemini 2.5 Mode**: Uses `@google/genai` with structured JSON schema outputs and low latency.
  - **Zero-Key Offline Simulation Mode (`--demo`)**: Fully functional offline mode allowing any reviewer or judge to run the multi-agent pipeline immediately without configuring an API key.
- **Multi-Modal Interfaces**:
  - **Rich Terminal UI**: Animated progress bars, colored status badges, findings summaries, and ANSI tables.
  - **Visual Web Dashboard (`--serve`)**: Embedded zero-dependency dark-mode dashboard (`http://localhost:3737`) featuring live score gauges, interactive diff viewer, agent timeline, and one-click GitHub PR review export.
- **Automated Patch Generation**: Produces copy-pasteable unified diff blocks that resolve discovered credential leaks and missing environment configurations.
- **Composite Readiness Scoring**: Generates an executive verdict (`APPROVED`, `NEEDS_REVIEW`, `REQUEST_CHANGES`) with an overall 0–100 PR readiness score.

---

## Technical Stack

- **Language & Runtime**: Node.js 18+ (tested on Node.js 22.17.1, ES Modules)
- **Agent Framework / Core Library**: Custom Autonomous Multi-Agent Orchestrator
- **LLM Provider & Models**: Google GenAI SDK (`@google/genai` v2.31.0) with `gemini-2.5-flash` / `gemini-2.5-pro`
- **Testing**: Native Node.js Test Runner (`node:test`, `node:assert`)
- **Dashboard & UI**: Built-in `node:http` server with modern HTML5/CSS3 glassmorphic UI and native ANSI terminal styling

---

## Architecture & Data Flow

```
                               ┌─────────────────────────────────────────┐
                               │           User / CI / GitHub PR         │
                               └────────────────────┬────────────────────┘
                                                    │
                                                    ▼
                               ┌─────────────────────────────────────────┐
                               │       Multi-Agent Orchestrator          │
                               │  (Git Diff Extractor & AST File Parser) │
                               └──────┬─────────────┬─────────────┬──────┘
                                      │             │             │
                 ┌────────────────────┘             │             └────────────────────┐
                 ▼                                  ▼                                  ▼
   ┌───────────────────────────┐      ┌───────────────────────────┐      ┌───────────────────────────┐
   │     SecuritySentinel      │      │     ComplianceAuditor     │      │       QualityCritic       │
   │  - Leaked API Keys Scanner│      │  - CONTRIBUTING Standards │      │  - Code Modularity        │
   │  - Shell & Exec Injections│      │  - Directory Isolation    │      │  - Error Resilience       │
   │  - Secret Redaction Engine│      │  - Template Completeness  │      │  - Async Safety           │
   └─────────────┬─────────────┘      └─────────────┬─────────────┘      └─────────────┬─────────────┘
                 │                                  │                                  │
                 └────────────────────┬─────────────┴──────────────────────────────────┘
                                      │ (Actionable Findings & Violations)
                                      ▼
                       ┌─────────────────────────────┐
                       │      PatchSynthesizer       │
                       │ - Generates Unified Diffs   │
                       │ - Auto-Redacts Leaked Keys  │
                       └──────────────┬──────────────┘
                                      │
                                      ▼
                       ┌─────────────────────────────┐
                       │     Executive Synthesis     │
                       │ - Composite Score (0-100)   │
                       │ - Verdict (PASS/WARN/FAIL)  │
                       │ - GitHub PR Review Markdown │
                       └──────┬───────────────┬──────┘
                              │               │
                 ┌────────────┴───┐       ┌───┴────────────┐
                 ▼                ▼       ▼                ▼
          [Terminal UI]    [Web Dashboard]  [JSON CI Stream] [GitHub Markdown]
```

---

## Prerequisites

Before running this project, ensure you have:
- **Node.js**: v18.0.0 or higher (Node.js 20+ or 22+ recommended). Check with `node --version`.
- **npm**: v9+ (check with `npm --version`).
- **Google Gemini API Key** *(Optional)*: Required only for live LLM reasoning. Obtain a free key at [Google AI Studio](https://aistudio.google.com/). If omitted, PR Sentinel automatically runs in simulation/demo mode.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/pr-sentinel
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Configure Environment Variables (Optional):**
   ```bash
   # On Linux/macOS:
   cp .env.example .env

   # On Windows (PowerShell):
   Copy-Item .env.example -Destination .env
   ```
   Open `.env` and paste your `GEMINI_API_KEY`. (Skip this step if running with `--demo`).

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `GEMINI_API_KEY` | No | *None* | Google Gemini API key. If unset, runs in deterministic simulation mode. |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Gemini model variant (`gemini-2.5-flash`, `gemini-2.5-pro`). |
| `MOCK_MODE` | No | `false` | When `true`, forces offline deterministic simulation mode. |
| `PORT` | No | `3737` | Local HTTP port for the embedded web dashboard. |
| `HOST` | No | `localhost` | Host interface for the embedded dashboard server. |
| `LOG_LEVEL` | No | `info` | Logging verbosity (`info`, `debug`, `warn`, `error`). |

---

## How to Run

### 1. Instant Multi-Agent Demonstration (Zero-Key)
Run an end-to-end evaluation with simulated vulnerability vectors, agent handoffs, and corrective patch synthesis:
```bash
npm run demo
# or
node src/cli.js --demo
```

### 2. Audit Current Directory or Local Git Branch
Audit the current git working tree or staged changes:
```bash
# Audit unstaged or recent commits
npm run audit

# Audit a specific directory
node src/cli.js audit --path .

# Audit only git staged changes
node src/cli.js --staged
```

### 3. Launch Local Visual Web Dashboard
Start the interactive glassmorphic web dashboard on `http://localhost:3737`:
```bash
npm run serve
# or
node src/cli.js --demo --serve
```

### 4. Interactive Terminal Console
Launch the interactive terminal prompt:
```bash
npm run dev
# or
node src/cli.js interactive
```

### 5. Generate Copy-Ready GitHub PR Review Comment
Output a formatted markdown report ready for pasting into GitHub Pull Request reviews:
```bash
node src/cli.js --demo --markdown
```

---

## Example Input & Output

### Example Command
```bash
node src/cli.js --demo
```

### Example Terminal Output
```
  ██████╗ ██████╗     ███████╗███████╗███╗   ██╗████████╗██╗███╗   ██╗███████╗██╗     
  ██╔══██╗██╔══██╗    ██╔════╝██╔════╝████╗  ██║╚══██╔══╝██║████╗  ██║██╔════╝██║     
  ██████╔╝██████╔╝    ███████╗█████╗  ██╔██╗ ██║   ██║   ██║██╔██╗ ██║█████╗  ██║     
  ██╔═══╝ ██╔══██╗    ╚════██║██╔══╝  ██║╚██╗██║   ██║   ██║██║╚██╗██║██╔══╝  ██║     
  ██║     ██║  ██║    ███████║███████╗██║ ╚████║   ██║   ██║██║ ╚████║███████╗███████╗
  ╚═╝     ╚═╝  ╚═╝    ╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚══════╝╚══════╝
  Autonomous Multi-Agent PR Review, Security Triage, and Auto-Patch System
  Powered by Google Gemini 2.5 & Google Developer Groups

Initiating Multi-Agent Pipeline...

  ▸ [Orchestrator] Initializing PR Sentinel Multi-Agent Review Pipeline
  ▸ [SecuritySentinel] Auditing for exposed credentials and dangerous code patterns
  ▸ [QualityCritic] Evaluating code architecture, error resilience, and maintainability
  ▸ [ComplianceAuditor] Verifying open-source repository guidelines & directory isolation
  ▸ [PatchSynthesizer] Synthesizing automated corrective diff patches
  ▸ [Orchestrator] Synthesizing executive PR readiness score and markdown review
  ▸ [Orchestrator] Review finished. Verdict: REQUEST_CHANGES (Score: 58/100)

Target Directory: .
Branch: feat/pr-sentinel  |  Commit: b0ad2a4
Files Scanned: 1  |  Duration: 1232ms

PR READINESS VERDICT:  FAIL   (Score: 58/100)
────────────────────────────────────────────────────────────────────────────

AGENT EXECUTION SUMMARY:
  • SecuritySentinel:    FAIL  Score: 10/100 (261ms)
    Scanned 1 files. Found 2 exposed secrets and 3 security observations.
  • ComplianceAuditor:   PASS  Score: 100/100 (264ms)
    Verified contribution structure against CONTRIBUTING.md checklist. Result: Compliant.
  • QualityCritic:       PASS  Score: 90/100 (264ms)
    Analyzed AST structure, error resilience, and code clarity across modified modules.
  • PatchSynthesizer:   2 patch(es) generated

KEY FINDINGS (4):
  [CRITICAL] Exposed gemini_api_key detected in agents/sample-agent/agent.js
    Location: agents/sample-agent/agent.js:10
    Issue:    Potential unredacted credential matching pattern for gemini_api_key found on line 10.
    Action:   Remove credential immediately, revoke the exposed key, and move to environment variables.

  [HIGH] Unsafe command execution in agents/sample-agent/agent.js
    Location: agents/sample-agent/agent.js:1
    Issue:    Direct call to eval() or exec() without proper input validation.
    Action:   Use execFile() with parameterized arguments and strict input sanitization.

AVAILABLE AUTO-PATCHES:
  • agents/sample-agent/agent.js: Replace hardcoded credential with process.env lookup in agents/sample-agent/agent.js
```

---

## How to Test

Run the automated test suite powered by the native Node.js test runner:

```bash
npm test
```

### Verified Test Suite Results
```bash
> pr-sentinel@1.0.0 test
> node --test tests/*.test.js

TAP version 13
ok 1 - Orchestrator executes full multi-agent pipeline deterministically in mock mode
ok 2 - Orchestrator generates clean markdown review report
ok 3 - compliance auditor verifies valid kebab-case folder name
ok 4 - compliance auditor checks presence of package manifest
ok 5 - compliance auditor flags isolation violations when PR modifies outside files
ok 6 - compliance auditor allows updating root agents/README.md index
ok 7 - parseUnifiedDiff correctly extracts changed files and additions/deletions
ok 8 - createLineReplacementPatch formats valid git unified diff
ok 9 - generateFixPatches generates patches for credential leaks
ok 10 - secrets scanner detects Gemini API keys
ok 11 - secrets scanner detects OpenAI API keys
ok 12 - secrets scanner detects AWS Access Keys
ok 13 - secrets scanner ignores placeholder values in .env.example
ok 14 - maskSecret safely truncates credentials

1..14
# tests 14
# suites 0
# pass 14
# fail 0
```

---

## Known Limitations

- **Binary Files**: Diff inspection is optimized for UTF-8 text files; binary assets (images, compiled archives) are excluded from AST and regex parsing.
- **Diff Size Cap**: Very large diffs exceeding `MAX_DIFF_LINES` (default 5,000 lines) are truncated to prevent context window overflow.
- **Git Context**: Requires a standard git working tree to extract commit diffs; when run outside a git repository, it falls back to inspecting local directory files.

---

## Security & Privacy Considerations

- **Zero Secrets Storage**: Never stores or logs plain-text API keys. Discovered credentials are automatically masked using partial prefix/suffix redaction (e.g., `AIza...5678`).
- **Sandboxed Analysis**: Operates strictly read-only on code files during review. Auto-patches are emitted as unified diffs and are not forcibly written without explicit user intent.
- **Local First**: All AST, regex scanning, compliance audits, and local web dashboards run entirely on `localhost`.

---

## Future Improvements

- [ ] GitHub Actions CI workflow integration to auto-comment reviews on PR open.
- [ ] Direct git commit applicator for approved auto-patches (`pr-sentinel apply`).
- [ ] Support for local LLM inference via Ollama (`llama3`, `deepseek-r1`).
- [ ] Semantic AST call graph analysis using Tree-sitter.

---

## License

*This project is contributed under the repository's open-source MIT license.*
