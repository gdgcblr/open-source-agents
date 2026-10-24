# 🛡️ PR Sentinel

> **Autonomous Multi-Agent Pull Request Review, Security Triage, and Auto-Patch System powered by Google Gemini.**

[![Tests: Passing](https://img.shields.io/badge/tests-14%2F14%20passing-brightgreen)](tests/)
[![Runtime: Node.js 18+](https://img.shields.io/badge/node-%3E%3D18.0.0-blue)](package.json)
[![LLM: Google Gemini 2.5](https://img.shields.io/badge/LLM-Gemini%202.5%20Flash%2FPro-orange)](https://aistudio.google.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 📑 Table of Contents
1. [Overview & Problem Statement](#overview)
2. [Key Capabilities](#key-capabilities)
3. [System Architecture & Data Flow](#architecture--data-flow)
4. [Codebase Anatomy & Directory Map](#codebase-anatomy)
5. [Prerequisites & Quickstart](#quickstart)
6. [Configuration & Environment Variables](#configuration--environment-variables)
7. [Running PR Sentinel (CLI, Demo, Dashboard, Markdown, PDF)](#how-to-run)
8. [Developer Guide: Extending PR Sentinel](#developer-guide-extending-pr-sentinel)
   - [How to Add a New Autonomous Agent](#how-to-add-a-new-agent)
   - [How to Add a New Static Scanner Tool](#how-to-add-a-new-scanner-tool)
   - [How to Add a New LLM Provider](#how-to-add-a-new-llm-provider)
9. [Automated Testing Suite](#automated-testing)
10. [Export Options (Markdown & Executive PDF)](#export-options)
11. [Security & Privacy Standards](#security--privacy-standards)
12. [Known Limitations & Future Roadmap](#known-limitations--future-roadmap)
13. [License](#license)

---

## Overview

### Problem Statement
Reviewing open-source pull requests is repetitive, slow, and prone to human oversight. Critical risks regularly slip through:
- **Credential & Secret Leaks**: Exposed API keys (Gemini, OpenAI, AWS, GitHub tokens) committed in code or git history.
- **Uncontained Code Execution**: Unsafe `eval()`, unescaped shell commands (`exec`), or unhandled infinite loops.
- **Repository Violations**: Non-conforming folder naming, missing manifests, unmaintained `.env.example`, or broken directory isolation.
- **Missing Remediation**: Reviewers spend hours writing repetitive review comments instead of providing actionable code patches.

### Solution: PR Sentinel
**PR Sentinel** is an autonomous multi-agent system designed for open-source maintainers, contributors, and hackathon teams. It automatically ingests pull requests, orchestrates four specialized AI agents to evaluate security, guidelines compliance, and code architecture, and synthesizes unified diff patches ready for merge.

---

## Key Capabilities

- **🤖 Orchestrated Multi-Agent Swarm**:
  - 🛡️ **`SecuritySentinel`**: High-accuracy scanner for 25+ secret patterns, private keys, dynamic code execution (`eval`), and unescaped shell calls.
  - 📋 **`ComplianceAuditor`**: Verifies repository contribution guidelines (`CONTRIBUTING.md`), directory naming (lowercase kebab-case), manifest tracking, and directory isolation.
  - 🏗️ **`QualityCritic`**: Reviews code modularity, error resilience, asynchronous exception handling, and code smells.
  - 🛠️ **`PatchSynthesizer`**: Synthesizes verified unified git diff patches to fix detected issues automatically.
- **⚡ Dual Execution Engine**:
  - **Live Gemini 2.5 Flash / Pro**: Structured reasoning powered by Google's official `@google/genai` SDK with strict JSON schema outputs.
  - **Zero-Key Deterministic Simulation Mode (`--demo`)**: Full offline execution with authentic agent handoffs, metrics, and patches without requiring paid API keys.
- **📊 Multi-Modal Interfaces**:
  - **Rich Terminal UI**: Native ANSI styling with step-by-step agent thinking, progress meters, and score badges.
  - **Embedded Web Dashboard (`http://localhost:3737`)**: Modern dark-mode glassmorphic dashboard with live score meters, diff viewers, and agent timelines.
  - **Downloadable Reports**: One-click export to GitHub PR review Markdown (`.md`) and human-readable executive audit PDFs (`.pdf`).

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
                       │ - Markdown & PDF Exporter   │
                       └──────┬───────────────┬──────┘
                              │               │
                 ┌────────────┴───┐       ┌───┴────────────┐
                 ▼                ▼       ▼                ▼
          [Terminal UI]    [Web Dashboard]  [JSON CI Stream] [Markdown / PDF]
```

### Composite Verdict Scoring Logic
- **`APPROVED`**: Composite score ≥ 85, 0 critical findings, compliance verified.
- **`NEEDS_REVIEW`**: Composite score 60–84, minor warnings, non-blocking items.
- **`REQUEST_CHANGES`**: Composite score < 60, exposed credentials, unsafe execution, or isolation violations.

---

## Codebase Anatomy

Here is the exact layout of the codebase to help you navigate and contribute:

```text
agents/pr-sentinel/
├── .env.example             # Sanitized environment variable template
├── .gitignore               # Ignores node_modules, .env, and build artifacts
├── package.json             # ES Module manifest, dependencies, and npm scripts
├── README.md                # Comprehensive documentation and developer handbook
├── src/
│   ├── config.js            # Environment loader, Gemini model config, fallback toggles
│   ├── cli.js               # Command-line interface and interactive menu runner
│   ├── agents/
│   │   ├── orchestrator.js  # Master pipeline: phase transitions, timing, composite scoring
│   │   ├── security.js      # SecuritySentinel agent implementation
│   │   ├── compliance.js    # ComplianceAuditor agent implementation
│   │   ├── quality.js       # QualityCritic agent implementation
│   │   └── patcher.js       # PatchSynthesizer agent implementation
│   ├── tools/
│   │   ├── secrets.js       # Regex & entropy secret scanner (Gemini, OpenAI, AWS, GitHub)
│   │   ├── compliance.js    # CONTRIBUTING.md validator, isolation & template checker
│   │   ├── git.js           # Git diff extractor, unified diff parser, file tree crawler
│   │   ├── ast.js           # Static AST pattern analyzer (eval, exec, unhandled exceptions)
│   │   └── patcher.js       # Unified diff generator & line replacement patch creator
│   ├── models/
│   │   ├── gemini.js        # Google GenAI SDK integration with JSON response formatting
│   │   └── mock.js          # Deterministic simulation engine for zero-key demo execution
│   └── ui/
│       ├── terminal.js      # ANSI banners, spinners, progress meters, and status tables
│       └── dashboard.js     # Zero-dependency embedded web server (:3737) with print styles
└── tests/
    ├── secrets.test.js      # Unit tests for credential detection and masking
    ├── compliance.test.js   # Unit tests for repository guidelines and isolation
    ├── git.test.js          # Unit tests for diff parsing and patch generation
    └── agents.test.js       # Integration tests for multi-agent pipeline orchestration
```

---

## Quickstart

### Prerequisites
- **Node.js**: `v18.0.0` or higher (tested on Node.js `v22.17.1`).
- **npm**: `v9.0.0` or higher.
- **Google Gemini API Key** *(Optional)*: If omitted, PR Sentinel automatically runs in offline simulation mode without failing.

### 1. Install Dependencies
```bash
cd agents/pr-sentinel
npm install
```

### 2. (Optional) Configure Gemini API Key
```bash
# On Linux/macOS:
cp .env.example .env

# On Windows (PowerShell):
Copy-Item .env.example -Destination .env
```
Edit `.env` and paste your `GEMINI_API_KEY`:
```env
GEMINI_API_KEY=AIzaSyYourKeyHere
```

### 3. Run the Instant Demo
```bash
npm run demo
```

---

## Configuration & Environment Variables

| Variable | Type | Default | Description |
| :--- | :---: | :--- | :--- |
| `GEMINI_API_KEY` | `string` | `""` | Google Gemini API key. If omitted, runs in mock simulation mode. |
| `GEMINI_MODEL` | `string` | `gemini-2.5-flash` | Gemini model variant (`gemini-2.5-flash`, `gemini-2.5-pro`). |
| `MOCK_MODE` | `boolean` | `false` | When `true`, forces deterministic offline simulation. |
| `PORT` | `number` | `3737` | Local HTTP port for the web dashboard server. |
| `HOST` | `string` | `localhost` | Host interface for the embedded dashboard server. |
| `LOG_LEVEL` | `string` | `info` | Logging verbosity (`info`, `debug`, `warn`, `error`). |
| `MAX_DIFF_LINES` | `number` | `5000` | Maximum git diff lines processed before truncation. |

---

## How to Run

### 1. Instant Multi-Agent Demonstration (Zero-Key)
Runs an end-to-end evaluation using simulated vulnerability vectors, demonstrating multi-agent coordination, secret detection, and auto-patching:
```bash
npm run demo
```

### 2. Audit Current Working Directory or Git Diff
Audit the repository or a specific target path:
```bash
# Audit current working tree
npm run audit

# Audit a specific folder
node src/cli.js audit --path agents/pr-sentinel

# Audit only git staged changes
node src/cli.js --staged

# Audit a branch comparison against main
node src/cli.js --base main
```

### 3. Launch Local Visual Web Dashboard
Starts the glassmorphic dark-mode web dashboard on `http://localhost:3737`:
```bash
npm run serve
```
Open **[http://localhost:3737](http://localhost:3737)** in any browser.

### 4. Interactive Terminal Session
Launches an interactive prompt menu:
```bash
npm run dev
```

### 5. Export Downloadable Reports
Save the review directly to a local Markdown file:
```bash
node src/cli.js --demo --output pr-review.md
```

---

## Developer Guide: Extending PR Sentinel

PR Sentinel is designed to be highly modular. New contributors can easily add new agents, static scanners, or LLM providers.

### How to Add a New Agent

All agents live in `src/agents/`. To create a new agent (e.g. `PerformanceAgent`):

1. **Create `src/agents/performance.js`**:
   ```javascript
   import { generateWithGemini } from '../models/gemini.js';
   import { config } from '../config.js';

   export class PerformanceAgent {
     constructor() {
       this.name = 'PerformanceAuditor';
     }

     async audit(context) {
       // 1. Run local inspection or prepare prompt
       const prompt = `Review performance bottlenecks in: ${JSON.stringify(context.files)}`;

       if (config.isLiveApiAvailable()) {
         const response = await generateWithGemini({
           systemInstruction: 'You are PerformanceAuditor. Identify O(n^2) operations and memory leaks.',
           prompt,
           jsonMode: true,
         });
         return response.data;
       }

       // 2. Return fallback simulation data
       return {
         agent: 'PerformanceAuditor',
         status: 'PASS',
         score: 95,
         findings: [],
       };
     }
   }
   ```

2. **Register it in `src/agents/orchestrator.js`**:
   - Import your agent: `import { PerformanceAgent } from './performance.js';`
   - Instantiate it in `Orchestrator.constructor`.
   - Call it in `Orchestrator.runReview()` and incorporate its score into `compositeScore`.

---

### How to Add a New Scanner Tool

All static analysis tools live in `src/tools/`. To add a new secret pattern or code rule:

1. **Add a pattern in `src/tools/secrets.js`**:
   ```javascript
   {
     name: 'HuggingFace Access Token',
     regex: /hf_[A-Za-z0-9]{34}/g,
     type: 'huggingface_token',
     severity: 'CRITICAL',
   }
   ```
2. **Add a test case in `tests/secrets.test.js`** to guarantee 100% test coverage!

---

### How to Add a New LLM Provider

LLM providers reside in `src/models/`. PR Sentinel currently supports Google Gemini via `@google/genai` and a deterministic simulation provider in `mock.js`.

To add another provider (e.g., Anthropic Claude or local Ollama):
1. Create `src/models/ollama.js`.
2. Implement a `generateWithOllama({ systemInstruction, prompt, jsonMode })` function.
3. Switch providers in `src/config.js` based on `process.env.LLM_PROVIDER`.

---

## Automated Testing

PR Sentinel uses the native Node.js test runner (`node:test` and `node:assert/strict`). It requires **zero extra test frameworks** and runs in milliseconds.

### Run All Tests
```bash
npm test
```

### Run a Specific Test Suite
```bash
node --test tests/secrets.test.js
node --test tests/compliance.test.js
node --test tests/git.test.js
node --test tests/agents.test.js
```

### Test Suite Coverage
- `tests/secrets.test.js`: Verifies detection of Gemini keys, OpenAI keys, AWS tokens, masking algorithms, and placeholder filtering.
- `tests/compliance.test.js`: Verifies kebab-case naming, manifest detection, and cross-project isolation checks.
- `tests/git.test.js`: Verifies unified diff parsing, chunk indexing, and line replacement patches.
- `tests/agents.test.js`: Verifies end-to-end multi-agent orchestration, state handoffs, and markdown report generation.

---

## Export Options

### 1. GitHub PR Review Markdown (`.md`)
Formatted specifically for GitHub review comments:
- Summary score table with emojis (`✅`, `⚠️`, `❌`).
- Detailed finding cards with file location and remediation steps.
- Expandable `<details>` tags enclosing unified diff codeblocks for auto-patches.

### 2. Human-Readable Executive PDF (`.pdf`)
- Clean, corporate A4 print layout styled via `@media print`.
- Numbered executive sections:
  1. Detailed Findings & Audit Observations
  2. Automated Remediation Patches (Unified Diffs)
  3. Multi-Agent Audit Trail & Execution Timeline
- Smart page-break protection (`page-break-inside: avoid`) preventing awkwardly split cards.
- Export by clicking **"📄 Export PDF"** on the Web Dashboard (`http://localhost:3737`).

---

## Security & Privacy Standards

- **Zero Secret Commits**: Real API keys are loaded strictly from `.env` and excluded via `.gitignore`.
- **Automatic Key Masking**: Exposed keys detected during audits are masked (e.g. `AIza...5678`) before being displayed in the UI, markdown, or logs.
- **Read-Only Inspection**: Code analysis and diff extraction are strictly read-only. Auto-patches are emitted as unified diffs and are never applied without explicit user approval.
- **Local-First Architecture**: Regex scanning, compliance audits, diff parsing, and local web dashboards run 100% on `localhost`.

---

## Known Limitations & Future Roadmap

### Known Limitations
- **Binary Assets**: Diff analysis is tailored for UTF-8 source code files; binary files (images, audio, compiled binaries) are ignored.
- **Diff Size Cap**: Changes exceeding `5,000` lines are truncated by default to prevent context overflow.

### Future Roadmap
- [ ] **GitHub Actions Workflow**: Auto-comment PR Sentinel audit reviews on incoming pull requests.
- [ ] **One-Click Patch Applicator**: CLI command `pr-sentinel apply --patch-id <id>` to directly apply generated diffs.
- [ ] **Ollama Integration**: Run local offline inference using open-weights models (`llama3`, `deepseek-r1`).
- [ ] **Tree-sitter Parser**: Language-specific AST call-graph tracing for complex multi-file refactoring.

---

## License

This project is contributed under the repository's open-source [MIT License](../../LICENSE).
