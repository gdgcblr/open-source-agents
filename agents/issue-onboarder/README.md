# Issue Onboarder Agent

> An open-source AI agent built with Google Agent Development Kit (ADK) and Gemini 2.5 Flash that inspects repository code to outline clear, beginner-friendly onboarding plans for new contributors.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Contributing to open-source projects can be daunting for first-time contributors. Issue descriptions are often concise or assume deep existing domain knowledge. Beginners frequently struggle to locate the relevant files, comprehend the architecture, set up the test environment, and adhere to project-specific contribution conventions.
- **Intended Users**: Open-source beginners, student developers, hackathon participants, and maintainers who want to provide automated, friendly onboarding guides for their repositories.

### Key Features
- **Live GitHub Issue Fetcher**: Uses `fetch_github_issue` to parse public GitHub issue URLs (e.g., `https://github.com/owner/repo/issues/123`) and retrieve live issue title, description, and labels via the public GitHub REST API.
- **Codebase-Aware Issue Review**: Features custom local inspection tools (`read_local_code_file` and `list_repository_files`) allowing the agent to read repository files, documentation, and existing code patterns.
- **Structured Contributor Onboarding Plan**: Produces an actionable markdown guide containing issue summary, architecture context, step-by-step implementation plan, testing commands, and git PR checklists.
- **Google ADK & Gemini 3.8 Flash**: Leverages Google's Agent Development Kit (`google-adk`) architecture, including native tool calling, session management, and `gemini-3.8-flash`.
- **Flexible Execution Modes**: Run with live GitHub URLs or text prompts via CLI flags (`--issue`), interactively via terminal, or through Google ADK's web interface (`adk web .`).

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework**: Google Agent Development Kit (`google-adk`)
- **LLM SDK**: Google GenAI (`google-genai`)
- **Model**: Gemini 2.5 Flash (`gemini-2.5-flash`)
- **Configuration & Secrets**: `python-dotenv`

---

## Architecture & Data Flow

```
[Contributor / User]
         │ (Submits Issue URL or Text Description)
         ▼
[CLI / ADK Runner] ──> [InMemorySessionService]
         │
         ▼
[Issue Onboarder Agent] ──> [Gemini 3.8 Flash]
         │                          ▲
         │ (Tool Execution Loop)    │
         ├──────────────────────────┤
         │ • fetch_github_issue()   │ ──> [GitHub REST API]
         │ • read_local_code_file() │
         │ • list_repository_files()│
         ▼                          │
[Local Repository Files & Docs] ────┘
         │
         ▼
[Structured Contributor Onboarding Plan (Markdown)]
```

The agent accepts an open-source issue prompt, calls local tools to inspect relevant source code, configuration, or contributor guidelines, reasons through the needed code changes, and formats a friendly, step-by-step plan.

---

## Prerequisites

Before running this project, ensure you have:
- **Python**: Version 3.10 or higher
- **Package Manager**: `pip`
- **Gemini API Key**: Obtainable from [Google AI Studio](https://aistudio.google.com/)

---

## Installation & Setup

1. **Navigate to the agent directory:**
   ```bash
   cd agents/issue-onboarder
   ```

2. **Create and activate a virtual environment:**
   - On Windows (PowerShell):
     ```powershell
     python -m venv .venv
     .venv\Scripts\activate
     ```
   - On Linux / macOS:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   # On Windows (PowerShell):
   Copy-Item .env.example .env

   # On Linux / macOS:
   cp .env.example .env
   ```
   Open `.env` and set your `GEMINI_API_KEY`:
   ```env
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   MODEL_NAME=gemini-2.5-flash
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes | *None* | Google Gemini API key from Google AI Studio |
| `MODEL_NAME` | No | `gemini-3.8-flash` | Identifier for the Gemini model (e.g., `gemini-3.8-flash`, `gemini-2.5-flash`) |

---

## How to Run

### Option 1: Direct CLI with a Live GitHub Issue URL
```bash
python agent.py --issue "https://github.com/gdgcblr/open-source-agents/issues/1"
```

### Option 2: Direct CLI with an Issue Text Argument
```bash
python agent.py --issue "Issue #42: Add support for custom timeout parameter in HTTP client utility"
```

### Option 3: Interactive Prompt Mode
```bash
python agent.py
```
Paste your issue description when prompted, and finish input (Ctrl+Z then Enter on Windows, or Ctrl+D on Linux/macOS).

### Option 3: Using Google ADK CLI
If you have the Google ADK CLI installed:
```bash
# Run via CLI
adk run .

# Run via ADK Web UI
adk web .
```

---

## Example Input & Output

### Example Input
```
Issue: Add a '--format json' option to the export CLI tool to allow exporting results as JSON in addition to CSV.
```

### Example Output
```markdown
# Contributor Onboarding Plan: Add JSON export option

Welcome to the project! Here is your step-by-step guide to tackling this issue:

### 1. Issue Summary & Context
The export CLI currently outputs data strictly in CSV format. This issue asks to add
a `--format` flag supporting `json`, so users can automate workflows that consume JSON.

### 2. Prerequisites & Environment Setup
- Python 3.10+
- Install dependencies: `pip install -r requirements.txt`
- Run existing tests to verify setup: `pytest tests/test_export.py`

### 3. Codebase Walkthrough
- `src/cli/export.py`: Handles command-line arguments using `argparse`.
- `src/formatters/`: Contains formatting logic (`csv_formatter.py`). We will add `json_formatter.py`.
- `tests/test_export.py`: Unit tests for exporter outputs.

### 4. Step-by-Step Implementation Guide
1. Create `src/formatters/json_formatter.py` with an `export_json(data)` helper.
2. In `src/cli/export.py`, add `--format` choice (`csv`, `json`) defaulting to `csv`.
3. Dispatch to `export_json()` when `--format json` is passed.

### 5. Local Testing & Verification
- Run: `python -m src.cli.export --format json --input sample.data`
- Run test suite: `pytest tests/`

### 6. Git & PR Checklist
- Create branch: `git checkout -b feat/json-export`
- Follow commit message format: `feat(cli): add --format json support`
- Open PR against `main` using the PR template.
```

---

## How to Test

### 1. Offline Syntax and Import Validation
Verify syntax and code compilation:
```bash
python -m py_compile agent.py
```

### 2. End-to-End Agent Execution
Ensure `GEMINI_API_KEY` is present in `.env`, then run:
```bash
python agent.py --issue "Test Issue: Add README section for troubleshooting common installation errors."
```
Confirm that the agent reads local files and outputs a formatted markdown plan.

---

## Known Limitations

- **Oversized Files**: Files larger than 100KB are automatically truncated to prevent exceeding context window budgets.
- **Local Filesystem Scope**: The agent reads local repository files; it does not directly modify files on disk without explicit user approval.
- **API Rate Limits**: Standard Gemini API rate limits and quotas apply according to your Google AI Studio plan.

---

## Security & Privacy Considerations

- **Zero Secrets**: Secrets are loaded exclusively via environment variables; `.env` is explicitly ignored in `.gitignore`.
- **Read-Only Access**: File reading tools operate in read-only mode and do not execute arbitrary shell commands.
- **Safe Path Resolution**: Paths are resolved and verified to prevent invalid directory traversal.

---

## Future Improvements

- [ ] Direct integration with the GitHub REST API to pull issues by URL or issue number.
- [ ] Interactive conversational mode for follow-up mentoring questions from contributors.
- [ ] Automatic scaffolding of initial test boilerplate for the proposed change.

---

## License

This project is contributed under the repository's [MIT License](../../LICENSE).
