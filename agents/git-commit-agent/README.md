# git-commit-agent

> An AI agent that analyses your staged git changes and generates a precise, conventional commit message — powered by Google ADK, Gemini, and offline Ollama.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Writing clean, informative, and standardized git commit messages is tedious. Developers often resort to vague commits ("fix bug", "updates") or spend disproportionate time formatting messages to meet team standards.
- **Intended Users**: Software engineers, open-source maintainers, and development teams seeking automated, consistent, and context-aware Conventional Commits.

### Key Features
- **Automatic Staged Diff & Stat Analysis**: Inspects both file-level change statuses and code diffs before generating suggestions.
- **Conventional Commits 1.0.0 Compliant**: Produces standard `<type>(<scope>): <description>` messages ready for semantic releases and changelogs.
- **Branch Context & Issue Auto-Linking**: Recognizes issue and ticket IDs from branch names (e.g. `feat/issue-123-auth` or `fix/PROJ-456`) and automatically suggests appropriate commit trailers (`Fixes #123`, `Refs: PROJ-456`).
- **One-Command Git Hook (`--install-hook`)**: Installs a `prepare-commit-msg` hook into `.git/hooks/` so running `git commit` automatically prefills your commit editor buffer with the generated message.
- **Dual Engine (Cloud & Offline)**: Supports Google Gemini via Google ADK 2.0 or local offline inference with Ollama (`qwen2.5-coder`, `llama3.2`) when working disconnected or with sensitive internal code.
- **Pre-Commit Secret & Credential Guard**: Automatically scans staged files and diffs for API keys, private keys, tokens, and `.env` files to prevent secret leakage.
- **Smart Noise Filtering**: Excludes noisy auto-generated lockfiles (`package-lock.json`, `poetry.lock`, etc.) to maximize relevant context window space.
- **Interactive Review & Multi-Turn Refinement**: Accept (`y`), edit in `$EDITOR` (`e`), cancel (`n`), or **regenerate with custom feedback** (`r`).
- **Amend Mode (`--amend`) & Soft Undo (`--undo`)**: Reads previous commit context for amending, or performs a safe soft reset (`--undo`) to restore staged changes if a typo occurred.
- **Atomic Commit Split Advisor (`--split`)**: Analyzes multi-file staged diffs and clusters them into recommended atomic Conventional Commits when multiple logical concerns are mixed together.
- **Custom Hints & Constraints**: Guide the agent with user hints (`-m / --hint`), enforced types (`--type feat`), and scopes (`--scope auth`).

---

## Technical Stack

- **Language & Runtime**: Python 3.11+
- **Agent Framework**: [Google Agent Development Kit (ADK) 2.0](https://github.com/google/adk-python)
- **Model Providers**: Google Gemini (AI Studio) or local Ollama instances
- **Other**: `python-dotenv` for configuration, Python `subprocess` for native Git integration, `unittest` for automated testing

---

## Architecture & Data Flow

```
[CLI Invocation: python main.py or 'git commit' hook]
      │
      ├─► 1. Pre-flight Checks (Git repository validation, .env loading)
      ├─► 2. Security Scan (Detect staged secrets, API keys, .env files)
      ├─► 3. Context Enrichment (Extract branch issue tags, e.g. #123)
      │
      ▼
[Engine Dispatcher: Google ADK 2.0 or Local Ollama]
      │
      ├─► Calls get_staged_file_summary()  ──► git diff --staged --name-status & --stat
      ├─► Calls get_staged_diff()          ──► git diff --staged (filtered lockfiles)
      └─► Calls get_last_commit_info()     ──► git log -1 (if --amend active)
      │
      ▼
[Agent synthesizes Conventional Commit message]
      │
      ▼
[Interactive Review Loop]
      ├─► [y]es         ──► git commit -m "<message>"
      ├─► [e]dit        ──► Opens $EDITOR, allows revision, loops back to confirm
      ├─► [r]egenerate  ──► Prompts for guidance, ADK agent regenerates in same session
      └─► [n]o          ──► Aborts cleanly without modifying Git history
```

---

## Prerequisites

- Python 3.11+
- `pip`
- `git` (2.25+) installed and available in `PATH`
- Either:
  - A Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey) (*cloud*), OR
  - [Ollama](https://ollama.ai) running locally (`ollama serve`) (*offline*)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/git-commit-agent
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # macOS / Linux
   # .venv\Scripts\activate    # Windows
   ```

3. **Install dependencies or install globally:**
   ```bash
   pip install -r requirements.txt
   # Or install locally with pipx / pip:
   pip install -e .
   ```

4. **Configure environment variables (for Gemini):**
   ```bash
   cp .env.example .env
   # Set GEMINI_API_KEY=<your key> in .env
   ```

---

## Configuration & Environment Variables

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes (for cloud) | *None* | Google AI Studio API key (*or set `GOOGLE_API_KEY`*) |
| `GOOGLE_API_KEY` | Optional | *None* | Fallback alias key |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Gemini model to use |
| `OLLAMA_HOST` | No | `http://localhost:11434` | Endpoint URL for offline local Ollama |
| `OLLAMA_MODEL` | No | `qwen2.5-coder:latest` | Model name for local Ollama runs |
| `EDITOR` | No | `vi` | Editor opened when choosing `e` in the interactive prompt |

---

## CLI Options & Usage

```bash
# Basic interactive mode: inspect staged changes and suggest commit
python main.py

# Preview the message without committing (dry run)
python main.py --dry-run

# Run offline using local Ollama model
python main.py --provider ollama

# Provide extra intent/context to guide the message
python main.py -m "Closes issue #102 and refactors token caching"

# Enforce a specific type or scope
python main.py --type feat --scope auth

# Stage all modified and deleted tracked files first (like git commit -a)
python main.py -a

# Amend the previous commit with updated staged changes
python main.py --amend

# Install / remove automatic Git hook into .git/hooks/prepare-commit-msg
python main.py --install-hook
python main.py --uninstall-hook

# Non-interactive mode (auto-commits without confirmation prompt)
python main.py -y
```

---

## How to Test

Run the automated test suite:
```bash
python -m unittest discover -s tests
```

---

## Security & Privacy Considerations

- **Zero Committed Secrets**: Sensitive values are stored exclusively in `.env` or environment variables; `.env` is ignored by `.gitignore`.
- **Pre-flight Secret Scanning**: Checks diffs for credentials before sending payloads to the LLM API, helping prevent accidental data leakage.
- **Offline Mode**: For internal or proprietary code, `--provider ollama` runs 100% on localhost without any network transmission.

---

## License

*Contributed under the project's open-source license.*
