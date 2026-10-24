# GitHub PR Reviewer & Triage Agent

> An automated, intelligent AI agent that reviews GitHub Pull Requests, analyzes diffs for security vulnerabilities and code smells, classifies PR size and risk, and generates actionable review reports.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Reviewing pull requests is time-consuming and prone to human oversight. Critical security flaws (such as hardcoded API keys, SQL injections, and command injection risks) and unhandled edge cases frequently slip through code reviews, while reviewers spend valuable engineering time on manual triage and sizing.
- **Intended Users**: Open-source maintainers, software engineers, DevOps/platform teams, and security reviewers seeking automated PR triage, pre-merge validation, and continuous code quality feedback.

### Key Features
- **Automated PR Triage**: Classifies pull requests by category (`Feature`, `Bug Fix`, `Security Fix`, `Refactor`, `Documentation`), size tier (`XS` to `XL`), and overall risk level (`Low`, `Medium`, `High`, `Critical`).
- **Heuristic Security & Secret Scanner**: Deterministic static checks detecting hardcoded secrets (AWS keys, GitHub tokens, private keys), SQL injection vectors, dangerous dynamic evaluation (`eval`/`exec`), disabled TLS verification, and leftover debug code.
- **LLM-Powered Reasoning & Synthesis**: Integrates with Google Gemini API (`gemini-1.5-flash`, `gemini-2.0-flash`, etc.) to provide contextual architectural analysis, constructive review notes, and line-by-line diff fix suggestions.
- **Dual-Mode Execution (Zero-Config Offline Support)**: Operates seamlessly in offline heuristic mode when an API key is not provided or when `--offline` is specified, ensuring 100% test reproducibility and zero paid API lock-in.
- **Multiple Input Sources**: Ingests diffs directly from live GitHub PR URLs (`https://github.com/owner/repo/pull/123`), repository slugs (`owner/repo#123`), local `.patch` / `.diff` files, or piped standard input (`git diff | python main.py --stdin`).
- **Flexible Output**: Generates GitHub-flavored markdown reports (ready for PR comments) or structured JSON payloads for CI/CD integration.

---

## Technical Stack

- **Language & Runtime**: Python 3.9+ / 3.10+ / 3.11+
- **Agent Framework / Core Library**: Custom multi-stage reasoning agent (Heuristic Pattern Engine + LLM Reviewer)
- **Models**: Google Gemini (`gemini-1.5-flash`, `gemini-1.5-pro`, configurable via `GEMINI_MODEL`)
- **External APIs / Tools**: GitHub REST API / Raw Diff endpoints, `requests`, `python-dotenv`
- **Testing**: `unittest` / `pytest`

---

## Architecture & Data Flow

```
[GitHub PR / Local Diff / Stdin]
              |
              v
     [Diff Parser Module]
              |
              +---> [Heuristic Rule Scanner]
              |            | (Secrets, Injections, Code Smells)
              |            v
              +---> [Triage & Sizing Engine]
              |            | (Type, Size Tier, Risk Level)
              |            v
              +---> [LLM Synthesis Agent (Gemini API)]
                           | (Architectural Analysis & Suggestions)
                           v
          [Structured Markdown / JSON Report]
```

1. **Diff Ingestion**: The agent fetches unified diffs from GitHub (API or web diff endpoint), a local patch file, or standard input.
2. **Unified Diff Parsing**: Changes are parsed into structured file diffs, hunk boundaries, and changed line arrays with line-number tracking.
3. **Static Heuristic Inspection**: Regex-based scanners evaluate additions for hardcoded credentials, known security anti-patterns, and code smells.
4. **Triage Metrics Computation**: Change volume and risk vectors are computed to categorize the pull request.
5. **AI Reasoning Loop**: If configured with a Gemini API key, diff context and heuristic observations are dispatched to Gemini for semantic review and code suggestions. In offline mode, the heuristic engine generates structured findings directly.
6. **Report Generation**: Output is formatted as a standardized markdown review report with triage metrics, findings by severity, and a reviewer checklist.

---

## Prerequisites

- **Python**: Python 3.9 or higher.
- **Package Manager**: `pip`
- **Gemini API Key (Optional)**: Required for LLM synthesis (`GEMINI_API_KEY`). If omitted, the agent runs in offline heuristic mode.
- **GitHub Token (Optional)**: Required only for private repositories or higher GitHub API rate limits.

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
   Copy the example environment configuration:
   ```bash
   cp .env.example .env
   ```
   *(Edit `.env` to supply `GEMINI_API_KEY` if you wish to enable LLM-powered review.)*

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | No | *None* | Google Gemini API key. If omitted, agent defaults to offline heuristic mode. |
| `GITHUB_TOKEN` | No | *None* | GitHub Personal Access Token (for private repos or high rate limits). |
| `GEMINI_MODEL` | No | `gemini-1.5-flash` | Gemini model name identifier (`gemini-1.5-flash`, `gemini-1.5-pro`). |
| `LOG_LEVEL` | No | `info` | Logging verbosity (`debug`, `info`, `warn`, `error`). |

---

## How to Run

### 1. Zero-Config Sample Run (Offline Heuristic Mode)
Run the agent on the bundled sample patch containing intentional security vulnerabilities:
```bash
python main.py --sample --offline
```

### 2. Review a Live Public GitHub Pull Request
```bash
python main.py --pr https://github.com/torvalds/linux/pull/42 --offline
# Or with LLM review enabled:
python main.py --pr https://github.com/facebook/react/pull/28000
```

### 3. Review a Local Git Diff or Patch File
```bash
python main.py --diff samples/sample_bug_fix.patch --offline
```

### 4. Pipe Uncommitted Local Git Changes via Stdin
```bash
git diff main...HEAD | python main.py --stdin --offline
```

### 5. Export Report to Markdown File or JSON
```bash
# Save to Markdown
python main.py --sample --offline --output pr_review.md

# Output structured JSON
python main.py --sample --offline --json
```

---

## Example Input & Output

### Example Input (Unified Diff)
```diff
diff --git a/src/auth/service.py b/src/auth/service.py
--- a/src/auth/service.py
+++ b/src/auth/service.py
@@ -10,6 +10,12 @@
+SECRET_KEY = "super-secret-production-jwt-key-do-not-share"
+
+def authenticate_user(username, password):
+    conn = sqlite3.connect("users.db")
+    cursor = conn.cursor()
+    query = f"SELECT * FROM users WHERE username = '{username}'"
+    cursor.execute(query)
```

### Example Output (Markdown Report)
````markdown
# 🤖 Pull Request Review & Triage Report

**Target:** `Sample PR Diff (sample_pr_diff.patch)`  
**Generated:** 2026-10-24 06:53:47 UTC  

---

## 📊 Triage Summary

| Metric | Assessment |
| :--- | :--- |
| **Type** | `Security Fix` |
| **Size** | `XS` (+19 / -2 lines across 2 files) |
| **Risk Level** | 🔴 Critical |

**Triage Note:** CRITICAL security issues found! Hardcoded credentials or critical flaws require immediate remediation.

---

## 🔍 Findings & Recommendations (4 issues identified)

### 1. 🚨 **CRITICAL**: Potential hardcoded secret or API key
- **Location:** `src/auth/service.py`:L14
- **Category:** `SECURITY`
- **Description:** Hardcoded sensitive data pattern matched on line 14.
- **Suggested Fix:**
```suggestion
Remove secret and load it from environment variables (`os.environ.get(...)`).
```

### 2. ⚠️ **HIGH**: Potential SQL injection: raw formatted string in SQL query
- **Location:** `src/auth/service.py`:L22
- **Category:** `SECURITY`
- **Description:** Identified risky programming construct on line 22.
- **Suggested Fix:**
```suggestion
Use parameterized queries with placeholder syntax (e.g. `cursor.execute('SELECT ... WHERE user = ?', (username,))`).
```

---

## ✅ Reviewer Checklist

- [ ] Verify all unit and integration tests pass cleanly.
- [ ] Verify that no sensitive environment variables or secrets are exposed.
- [ ] Ensure adequate test coverage has been added for modified code paths.
- [ ] Check for edge cases and input validation on external data.
````

---

## How to Test

Run the automated test suite using `unittest`:

```bash
# Run all tests
python -m unittest discover -s tests -v

# Or with pytest
pytest tests/
```

### Test Coverage Summary:
- **`test_parse_pr_target`**: Validates URL and repo/number slug parsing.
- **`test_parse_unified_diff`**: Validates multi-file diff parsing, hunk calculation, and line numbers.
- **`test_heuristic_security_detection`**: Validates regex detection of AWS keys, hardcoded JWT secrets, and SQL injections.
- **`test_calculate_triage`**: Validates sizing thresholds and risk classification.
- **`test_end_to_end_offline_analysis`**: Verifies complete end-to-end report generation and markdown/JSON formatting.

---

## Known Limitations

- **Large PR Truncation**: Extremely large diffs (>50,000 lines) are truncated to respect model context window boundaries.
- **Private Repository Access**: Analyzing private GitHub PRs requires exporting `GITHUB_TOKEN` with appropriate repository read scopes.
- **Dynamic Language Constraints**: Static heuristic checks use regex patterns and do not perform deep inter-procedural data flow tracking (complemented by Gemini LLM analysis when enabled).
