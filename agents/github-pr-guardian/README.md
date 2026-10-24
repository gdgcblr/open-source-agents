# 🛡️ GitHub PR Guardian

> An autonomous security auditor and intelligent code review agent powered by Google Gemini, designed to automatically triage PRs, flag security vulnerabilities, catch hallucinated dependencies, and enforce open-source quality standards.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: In collaborative open-source monorepos and hackathons, maintainers face an overwhelming deluge of pull requests. Reviewing each PR for leaked API credentials, dangerous code executions (`eval`, unsafe SQL), typosquatted dependencies, and adherence to repository guidelines is time-consuming and error-prone.
- **Intended Users**: Open-source maintainers, DevOps/DevSecOps engineers, and developers who want automated, instant pre-merge feedback on their feature branches before submitting PRs.

### Key Features
- **Deterministic Static Pre-Scan**: Zero-latency detection of leaked credentials (AWS keys, GitHub personal access tokens, private keys, generic secrets) and dangerous runtime calls (`eval()`, `exec()`, `shell=True`, unsanitized SQL string formatting).
- **Intelligent LLM Reasoning**: Powered by Google Gemini (`gemini-2.5-flash`), evaluating complex architectural patterns, edge cases, error handling, and code maintainability.
- **Dependency Provenance Checks**: Audits additions to `requirements.txt` and `package.json` to flag unpinned or suspicious packages.
- **Multi-Source Ingestion**:
  - Live GitHub Pull Requests via URL or `owner/repo#number`
  - Local working directory changes (`--git`) and staged changes (`--staged`)
  - Standalone `.diff` and `.patch` files (`--diff path/to/file.diff`)
- **Ready-to-Post Markdown Reviews**: Generates formatted GitHub review comments complete with verdicts (`APPROVE`, `REQUEST_CHANGES`, `COMMENT`), a risk scorecard (0–100), file:line pointers, and actionable remediations.
- **Offline / Zero-Config Mode**: Can run in pure static heuristic mode (`--no-llm`) with zero API keys or external dependencies required.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Reasoning**: Google Gemini API (`gemini-2.5-flash` or `gemini-1.5-flash`) with structured schema generation
- **APIs & Protocols**: GitHub REST API v3 (for PR metadata and unified diff extraction)
- **Heuristics Engine**: Regex-based token pattern matching and static AST pattern checks
- **Output Formats**: Terminal ANSI / Rich UI and GitHub Flavored Markdown

---

## Architecture & Data Flow

```
                     +---------------------------------------+
                     |         Input Sources                 |
                     |  - GitHub PR (URL / API)              |
                     |  - Local Git (Working / Staged)       |
                     |  - File (.diff / .patch)              |
                     +---------------------------------------+
                                         |
                                         v
                     +---------------------------------------+
                     |          Unified Diff Parser          |
                     |   Parses files, hunks, line mappings  |
                     +---------------------------------------+
                                         |
                    +--------------------+--------------------+
                    |                                         |
                    v                                         v
   +---------------------------------+       +---------------------------------+
   |      Static Rules Scanner       |       |       Context Pre-Formatter     |
   | - Leaked API secrets            |       | Aggregates diff chunks, file    |
   | - SQLi / eval / shell=True      |       | boundaries, and metadata        |
   | - Suspicious dependencies       |       +---------------------------------+
   +---------------------------------+                        |
                    |                                         |
                    +--------------------+--------------------+
                                         |
                                         v
                     +---------------------------------------+
                     |          Google Gemini 2.5            |
                     |  - Deep semantic code review          |
                     |  - Architecture & quality evaluation  |
                     |  - Test coverage gap detection        |
                     +---------------------------------------+
                                         |
                                         v
                     +---------------------------------------+
                     |         Review Reporter Agent         |
                     |  - Terminal Scorecard & Risk Meter    |
                     |  - GitHub PR Markdown Review Export   |
                     +---------------------------------------+
```

---

## Prerequisites

- **Python**: Python 3.10 or higher
- **Package Manager**: `pip` (Python standard library is also fully supported as fallback)
- **API Keys**: 
  - `GEMINI_API_KEY`: Required for full AI reasoning (get free key at [Google AI Studio](https://aistudio.google.com/)).
  - `GITHUB_TOKEN`: Optional (for higher rate limits when fetching public/private GitHub PRs).

---

## Installation & Setup

1. **Navigate to the agent directory:**
   ```bash
   cd agents/github-pr-guardian
   ```

2. **(Optional) Set up a virtual environment and install dependencies:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
   *(Note: The agent is engineered to gracefully run using standard Python 3 libraries if external packages are not installed.)*

3. **Configure Environment Variables:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and supply your `GEMINI_API_KEY`:
   ```bash
   GEMINI_API_KEY=your_gemini_api_key_here
   GEMINI_MODEL=gemini-2.5-flash
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Recommended | *None* | Google AI Studio API Key for LLM reasoning |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Gemini model to use for analysis |
| `GITHUB_TOKEN` | No | *None* | Personal Access Token to avoid GitHub API rate limits |

---

## How to Run

### 1. Review bundled sample test diffs
```bash
# Review a vulnerable sample diff (finds leaked keys, SQLi, and eval)
python3 main.py --diff sample_diffs/vulnerable_pr.diff

# Review a clean sample diff
python3 main.py --diff sample_diffs/clean_pr.diff
```

### 2. Review a live GitHub Pull Request
```bash
python3 main.py --pr https://github.com/owner/repository/pull/42
```

### 3. Review your current local changes before committing
```bash
# Review uncommitted working tree changes
python3 main.py --git

# Review staged changes
python3 main.py --staged
```

### 4. Export review report to Markdown
```bash
python3 main.py --diff sample_diffs/vulnerable_pr.diff --output pr_review.md
```

### 5. Run in offline mode (No API Key needed)
```bash
python3 main.py --diff sample_diffs/vulnerable_pr.diff --no-llm
```

---

## Example Input & Output

### Example Input
Analyzing `sample_diffs/vulnerable_pr.diff` which adds:
```python
AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
return eval(script_str)
```

### Example Terminal Output
```
======================================================================
🛡️  GITHUB PR GUARDIAN — AUTOMATED CODE REVIEW REPORT
======================================================================
Verdict: ❌ CHANGES REQUESTED
Risk Score: 90/100 [CRITICAL]
----------------------------------------------------------------------
Executive Summary:
Critical security risks detected in new authentication module. Hardcoded AWS
credentials, potential SQL injection in user query, and arbitrary code execution
via eval().

🔍 Identified Findings & Recommendations:

  [CRITICAL] AWS Access Key ID (Static Rule)
  Location: src/auth.py:5
  Details:  Found potential secret pattern in added code: `AKIAIO...`
  Fix:      Revoke key immediately and use AWS IAM roles or environment variables.

  [HIGH] Potential SQL Injection (String Interpolation) (AI Reasoning)
  Location: src/auth.py:13
  Details:  User-supplied parameters are interpolated directly into raw SQL.
  Fix:      Use parameterized queries or ORM query builders to prevent SQL injection.

  [HIGH] Arbitrary Code Execution (eval/exec) (Static Rule)
  Location: src/auth.py:19
  Details:  Potential vulnerability: Arbitrary Code Execution (eval/exec)
  Fix:      Avoid dynamic evaluation of code. Use explicit parsing (e.g. ast.literal_eval).

  [INFO] Dependency Added / Modified (Static Rule)
  Location: requirements.txt:2
  Details:  New dependency registered: `reqeusts==2.31.0`. Verify provenance.
  Fix:      Ensure the package name is authentic and version is pinned.

🧪 Recommended Tests:
  • Unit test verifying parameterized SQL query with SQL meta-characters.
  • Test suite verifying that secrets are loaded from environment variables.
======================================================================
```

---

## How to Test

You can verify the agent using either the included test diffs or the Python test suite:

```bash
# Test 1: Verify detection on vulnerable diff
python3 main.py --diff sample_diffs/vulnerable_pr.diff --no-llm

# Test 2: Verify clean diff passing without false positives
python3 main.py --diff sample_diffs/clean_pr.diff --no-llm

# Test 3: Verify local git diff review
git diff HEAD > temp.diff && python3 main.py --diff temp.diff --no-llm && rm temp.diff
```

---

## Known Limitations

- **Diff Context Truncation**: Extremely large monolithic PRs (>100,000 characters) are truncated to fit within model context windows.
- **Binary Files**: Binary files (e.g., compiled `.so`, `.png`, `.zip`) are identified but not inspected for secrets.
- **Private Repositories**: To analyze private GitHub repositories, a `GITHUB_TOKEN` with `repo` scope must be provided.

---

## Security & Privacy Considerations

- **Secrets Handling**: Environment variables are loaded strictly from the local `.env` or system environment. The repository `.gitignore` explicitly prevents `.env` from being checked into Git.
- **Data Privacy**: Only the git diff text is sent to the Google Gemini API for review synthesis. No local system files or uncommitted workspace files outside the diff are ever accessed or transmitted.
- **Safe Execution**: The agent only performs read operations and diff parsing; it does not execute any code contained within the analyzed pull requests.

---

## Future Improvements

- [ ] Add GitHub Actions CI/CD workflow to post automated comments directly back to the GitHub PR.
- [ ] Add support for local offline LLMs using Ollama (e.g., Gemma 2 or Qwen 2.5 Coder).
- [ ] Add Semgrep / Bandit integration for extended static vulnerability scanning.

---

## License

This project is contributed under the repository's open-source license.
