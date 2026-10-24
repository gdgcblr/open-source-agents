# pr-reviewer

> An autonomous AI agent powered by Google ADK and Gemini that performs security audits, performance reviews, and quality checks on Pull Request code diffs.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Reviewing large Pull Requests is time-consuming, and critical security vulnerabilities, performance anti-patterns (such as N+1 queries), and subtle logic bugs frequently slip into production codebases.
- **Intended Users**: Software engineering teams, open-source maintainers, and individual developers seeking pre-merge automated security and quality audits.

### Key Features
- **Multi-Pillar Audits**:
  - 🛡️ **Security & OWASP Top 10**: Checks for injection, unvalidated inputs, credential leaks, and insecure API exposures.
  - 🌐 **Blast Radius & Surface Impact**: Computes quantitative risk scores (0-100) based on churn, sensitive surface modifications (auth, db schemas, configs), and visual risk heatmaps.
  - ⚡ **Performance & Scalability**: Detects algorithmic bottlenecks, blocking operations, and resource leaks.
  - 🧼 **Code Quality**: Enforces error handling, maintainability, modularity, and language best practices.
- **Surrounding Context Inspection**: Uses Google ADK tools to not only read diffs but also pull surrounding file contents (`read_repo_file`) when context is ambiguous.
- **Clear Review Decision**: Concludes each review with an explicit action recommendation: `APPROVE`, `COMMENT`, or `REQUEST_CHANGES`.
- **Structured Markdown Output**: Generates GitHub-ready markdown tables, inline fix proposals, and highlights.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+
- **Agent Framework**: [Google Agent Development Kit (ADK) 2.0](https://github.com/google/adk-python)
- **Model**: Gemini 2.0 Flash (configurable via `GEMINI_MODEL`)
- **Dependencies**: `google-adk`, `python-dotenv`

---

## Prerequisites

- Python 3.11+
- `git` installed and available in `PATH`
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey)

---

## Installation & Setup

1. **Navigate to the directory:**
   ```bash
   cd agents/pr-reviewer
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Set GEMINI_API_KEY=<your key> in .env
   ```

---

## CLI Options & Usage

```bash
# Review current branch against main
python main.py

# Review against a specific base branch or remote
python main.py --base origin/main

# Review only currently staged Git changes
python main.py --staged

# Save output to a markdown report
python main.py --base main -o pr-review.md
```

---

## How to Test

Run the automated test suite:
```bash
python -m unittest discover -s tests
```

---

## License

*Contributed under the project's open-source license.*
