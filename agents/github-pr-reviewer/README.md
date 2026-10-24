# Autonomous GitHub PR Reviewer & Triage Council

> A multi-agent AI system that audits GitHub Pull Requests for OWASP/CWE security vulnerabilities and performance bottlenecks, autonomously synthesizes regression tests, authors drop-in remediation patches, and issues definitive merge verdicts.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Reviewing pull requests is time-consuming, mentally exhausting, and prone to human oversight. Critical security vulnerabilities (hardcoded secrets, SQL injections, command injection vectors) and subtle performance regressions frequently slip past reviewers, while engineering teams lack the bandwidth to author missing unit tests or fix boilerplate issues for external contributors.
- **Intended Users**: Open-source maintainers, software engineering teams, platform/DevOps leads, and security auditors seeking fully autonomous, pre-merge PR triage and self-healing pull request reviews.

### Key Features
- **Multi-Agent Specialist Council**: Coordinates four specialized AI agents to deliver multi-faceted code reviews:
  1. **Security & Vulnerability Auditor**: Scans additions against OWASP Top 10 and CWE standards (CWE-798, CWE-89, CWE-78, CWE-95, CWE-502, CWE-295).
  2. **Performance & Reliability Architect**: Flags unmanaged database connections, resource leaks, full-table scans, and blocking synchronous calls.
  3. **Automated Test Synthesizer**: Parses touched function signatures and automatically writes complete, runnable `pytest` unit and regression test cases.
  4. **Lead Architect (Adjudicator)**: Evaluates specialist reports, computes a composite Code Health Score (0–100), and renders a definitive verdict (`APPROVED`, `CHANGES_REQUESTED`, or `BLOCKED`).
- **Autonomous Remediation Patching (`--auto-fix`)**: Authors an apply-ready `remediation.patch` file containing concrete drop-in fixes that developers can apply in one command (`git apply remediation.patch`).
- **Interactive Dark-Mode HTML Dashboard (`--html`)**: Generates a self-contained, offline-compatible HTML report featuring SVG health score gauges, council scorecards, filterable findings, and copy-pasteable test cases.
- **Drop-in GitHub Action**: Packaged with a native [`action.yml`](action.yml) for 1-click installation into any repository's CI/CD pipeline.
- **Rich Terminal UI & Visual Scorecard**: Terminal interface with progress indicators, colored scorecard tables, and severity panels (with graceful ANSI fallback).
- **Dual-Mode Zero-Config Offline Support**: Operates out-of-the-box in local heuristic mode without requiring any API keys, with optional Gemini LLM deep synthesis (`gemini-1.5-flash`, `gemini-1.5-pro`).

---

## Technical Stack

- **Language & Runtime**: Python 3.9+ / 3.10+ / 3.11+
- **Agent Architecture**: Multi-Agent Orchestration (Specialist Council Pattern)
- **Supported Models**: Google Gemini (`gemini-1.5-flash`, `gemini-1.5-pro` via official REST API)
- **CLI & Presentation**: Python `rich` (with zero-dependency ANSI fallback)
- **CI/CD Integration**: GitHub Actions Composite Action (`action.yml`)
- **Testing**: Python `unittest` / `pytest`

---

## Architecture & Data Flow

```
                     [GitHub PR / Local Diff / Stdin]
                                    │
                                    ▼
                         [Unified Diff Parser]
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    ▼                               ▼                               ▼
[Security Auditor]        [Performance Architect]         [Test Synthesizer]
 • CWE-798 (Secrets)       • Resource & Connection Leaks   • Function AST Inspection
 • CWE-89 (SQL Injection) • Full-Table Scans               • Edge-case Test Authoring
 • CWE-78 (Cmd Injection) • Blocking Event Loop Calls     • Pytest Suite Generation
    │                               │                               │
    └───────────────────────────────┼───────────────────────────────┘
                                    ▼
                        [Lead Architect Agent]
                                    │
                   ┌────────────────┴────────────────┐
                   ▼                                 ▼
         [Composite Health Score]            [Definitive Verdict]
             (Weighted 0–100)           (APPROVED / CHANGES / BLOCKED)
                   │                                 │
                   └────────────────┬────────────────┘
                                    ▼
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
[Rich Terminal UI]         [Interactive HTML]        [Auto-Fix Patch]
 Scorecard & Tables         Standalone Dashboard       remediation.patch
```

---

## Prerequisites

- **Python**: Python 3.9 or higher.
- **Package Manager**: `pip`
- **Gemini API Key (Optional)**: Required for deep generative LLM review (`GEMINI_API_KEY`). If omitted, the agent runs in offline specialist council mode with zero external dependencies.
- **GitHub Token (Optional)**: Required only for private repositories or high GitHub API rate limits.

---

## Installation & Setup

1. **Navigate to the agent directory:**
   ```bash
   cd agents/github-pr-reviewer
   ```

2. **Set up a virtual environment and install dependencies:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   ```bash
   cp .env.example .env
   ```
   *(Edit `.env` to supply `GEMINI_API_KEY` for online LLM synthesis.)*

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | No | *None* | Google Gemini API key. If omitted, agent runs in offline council mode. |
| `GITHUB_TOKEN` | No | *None* | GitHub Personal Access Token (for private repos or higher API limits). |
| `GEMINI_MODEL` | No | `gemini-1.5-flash` | Gemini model name identifier (`gemini-1.5-flash`, `gemini-1.5-pro`). |
| `LOG_LEVEL` | No | `info` | Logging verbosity (`debug`, `info`, `warn`, `error`). |

---

## How to Run

### 1. Zero-Config Sample Run (Offline Council Mode)
Run the agent on the bundled sample patch containing intentional security vulnerabilities:
```bash
python main.py --sample --offline
```

### 2. Autonomous Self-Healing Verification Loop
Simulate applying the remediation patch and compare **Before vs After** health scorecards:
```bash
python main.py --sample --offline --verify-healing
```

### 3. Autonomous Auto-Fix & Test Synthesis
Generate a remediation patch and unit test suite:
```bash
python main.py --sample --offline --auto-fix --generate-tests generated_tests.py
```
To apply the generated fixes to your local branch:
```bash
git apply remediation.patch
```

### 4. Zero-Dependency Local Web Server UI
Launch an interactive dark-mode web dashboard in your browser:
```bash
python main.py --serve 8080
# Open http://localhost:8080 in your browser!
```

### 5. Install Git Pre-Push Hook
Automatically prevent anyone on the team from pushing code with hardcoded secrets or SQL injections:
```bash
python main.py --install-hook
```

### 6. Export Interactive HTML Dashboard
Export a standalone, dark-mode HTML dashboard file:
```bash
python main.py --sample --offline --html pr_dashboard.html
```

### 7. Review a Live Public GitHub Pull Request
```bash
python main.py --pr https://github.com/torvalds/linux/pull/42 --offline
# Or post review directly as a PR comment:
python main.py --pr https://github.com/owner/repo/pull/123 --comment
```
# Or with Gemini LLM enabled:
python main.py --pr https://github.com/facebook/react/pull/28000
```

### 5. Review Uncommitted Git Changes via Stdin
```bash
git diff main...HEAD | python main.py --stdin --offline
```

### 6. Run in CI Mode (Exit Code 1 on BLOCKED)
```bash
python main.py --diff my_feature.patch --ci
```

---

## GitHub Action Integration

Add the agent to any repository's CI pipeline by creating `.github/workflows/pr-agent.yml`:

```yaml
name: "AI PR Reviewer Council"
on:
  pull_request:
    branches: [main]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: Mourya-N/open-source-agents/agents/github-pr-reviewer@feat/github-pr-reviewer
        with:
          gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
          auto_fix: "true"
          fail_on_block: "true"
```

---

## Example Input & Output

### Terminal Council Scorecard Output
```text
╭──────── 🤖 PR Council Review: Sample PR Diff (sample_pr_diff.patch) ─────────╮
│                                                                              │
│   VERDICT: BLOCKED  |  HEALTH SCORE: 40/100                                  │
│                                                                              │
╰──────────────────────────────────────────────────────────────────────────────╯
                      🏛️ Specialist Agent Council Scorecard                      
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Specialist Agent          ┃ Health Score ┃ Status ┃ Key Observation          ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Security & Vulnerability  │    0/100     │ FAILED │ Detected 3 critical or   │
│ Auditor                   │              │        │ high security issue(s).  │
│ Performance & Reliability │   75/100     │ PASSED │ Resource management and  │
│ Architect                 │              │        │ I/O patterns meet norms. │
│ Automated Test            │   70/100     │ PASSED │ Synthesized 1 automated  │
│ Synthesizer               │              │        │ test case(s).            │
└───────────────────────────┴──────────────┴────────┴──────────────────────────┘
               📊 Triage & Sizing Analysis               
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Classification ┃ Size Tier ┃ Lines (+/-) ┃ Risk Level ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│  Security Fix  │    XS     │  +19 / -2   │  Critical  │
└────────────────┴───────────┴─────────────┴────────────┘

🔍 Findings & Remediation (6 identified):
1. [CRITICAL] Potential hardcoded secret or API key [CWE-798: Hardcoded Credentials]
   Location: src/auth/service.py:14
   Fix: Extract secret to environment variables or secret manager vault.
2. [HIGH] Potential SQL injection: formatted f-string in SQL query [CWE-89: SQL Injection]
   Location: src/auth/service.py:22
   Fix: Use parameterized SQL query binding with placeholders (?, %s, or :param).

╭──────────────── 🩹 Autonomous Remediation Patch (git apply) ─────────────────╮
│ diff --git a/src/auth/service.py b/src/auth/service.py                       │
│ --- a/src/auth/service.py                                                    │
│ +++ b/src/auth/service.py                                                    │
│ @@ -13,5 +13,5 @@                                                            │
│ -SECRET_KEY = "super-secret-production-jwt-key-do-not-share"                 │
│ +SECRET_KEY = os.environ.get('SECRET_KEY')                                   │
╰──────────────────────────────────────────────────────────────────────────────╯
```

---

## How to Test

Run the automated test suite covering all specialist agents, test generator, patch generator, and dashboard reporter:

```bash
python3 -m unittest discover -s tests -v
```

### Test Suite Coverage:
- `test_security_specialist_agent`: Validates OWASP/CWE pattern detection, secret flags, and failure status.
- `test_performance_specialist_agent`: Validates resource leak and query scanning.
- `test_auto_test_generator_agent`: Validates AST function discovery and unit test code synthesis.
- `test_auto_patch_generator`: Verifies authoring of valid unified git diff patches.
- `test_html_dashboard_generation`: Validates full standalone HTML generation with SVG health gauge.
- `test_end_to_end_council_verdict_blocked`: Validates adjudication of blocked PRs and patch bundling.
- `test_end_to_end_council_verdict_approved`: Validates approval workflows for clean bug fixes.
- `test_parse_pr_target`: Validates GitHub URL and slug parsing.
- `test_parse_unified_diff`: Validates multi-file diff parsing with hunk tracking.

---

## Known Limitations

- **Large PR Truncation**: Diffs exceeding 50,000 characters are safely truncated to respect LLM context window constraints.
- **Language Coverage for Tests**: Automated test generation currently synthesizes Python `pytest` test suites; multi-language test generation for TypeScript/Go is on the roadmap.
- **Private Repository Scopes**: Inspecting private pull requests requires providing a GitHub Personal Access Token with repo read scopes.
