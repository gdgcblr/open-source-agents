# git-commit-agent

> An AI agent that analyses your staged git changes and generates a precise, conventional commit message — powered by Google ADK and Gemini.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Writing clean, informative, and standardized git commit messages is tedious. Developers often resort to vague commits ("fix bug", "updates") or spend disproportionate time formatting messages to meet team standards.
- **Intended Users**: Software engineers, open-source maintainers, and development teams seeking automated, consistent, and context-aware Conventional Commits.

### Key Features
- **Automatic Staged Diff & Stat Analysis**: Inspects both file-level change statuses and code diffs before generating suggestions.
- **Conventional Commits 1.0.0 Compliant**: Produces standard `<type>(<scope>): <description>` messages ready for semantic releases and changelogs.
- **Pre-Commit Secret & Credential Guard**: Automatically scans staged files and diffs for API keys, private keys, tokens, and `.env` files to prevent secret leakage.
- **Smart Noise Filtering**: Excludes noisy auto-generated lockfiles (`package-lock.json`, `poetry.lock`, etc.) to maximize relevant context window space.
- **Interactive Review & Multi-Turn Refinement**: Accept (`y`), edit in `$EDITOR` (`e`), cancel (`n`), or **regenerate with custom feedback** (`r`).
- **Amend Mode (`--amend`)**: Reads previous commit context and staged revisions to regenerate messages for amending commits.
- **Custom Hints & Constraints**: Guide the agent with user hints (`-m / --hint`), enforced types (`--type feat`), and scopes (`--scope auth`).
- **Flexible Automation**: Includes `--dry-run`, auto-staging (`-a`), non-interactive execution (`-y`), and model selection (`--model`).

---

## Technical Stack

- **Language & Runtime**: Python 3.11+
- **Agent Framework**: [Google Agent Development Kit (ADK) 2.0](https://github.com/google/adk-python)
- **Model**: Gemini 2.0 Flash (configurable via `GEMINI_MODEL` or `--model`)
- **External APIs**: Google Gemini API via Google AI Studio
- **Other**: `python-dotenv` for configuration, Python `subprocess` for native Git integration

---

## Architecture & Data Flow

```
[CLI Invocation: python main.py]
      │
      ├─► 1. Pre-flight Checks (Git repository validation, .env loading, API key check)
      ├─► 2. Security Scan (Detect staged secrets, API keys, .env files)
      │
      ▼
[Google ADK Runner + InMemorySessionService]
      │
      ├─► Calls get_staged_file_summary()  ──► git diff --staged --name-status & --stat
      ├─► Calls get_staged_diff()          ──► git diff --staged (filtered lockfiles)
      └─► Calls get_last_commit_info()     ──► git log -1 (if --amend active)
      │
      ▼
[ADK Agent synthesizes Conventional Commit message]
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
- A Gemini API key — get one free at [Google AI Studio](https://aistudio.google.com/app/apikey)

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

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Open .env and set GEMINI_API_KEY=<your key>
   ```
   *(Note: If you already have `GOOGLE_API_KEY` set in your shell environment, it will be automatically detected.)*

---

## Configuration & Environment Variables

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes* | *None* | Google AI Studio API key (*or set `GOOGLE_API_KEY`*) |
| `GOOGLE_API_KEY` | Optional | *None* | Alternative fallback key environment variable |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Gemini model to use |
| `EDITOR` | No | `vi` | Editor opened when choosing `e` in the interactive prompt |

---

## CLI Options & Usage

```bash
# Basic interactive mode: inspect staged changes and suggest commit
python main.py

# Preview the message without committing (dry run)
python main.py --dry-run

# Provide extra intent/context to guide the message
python main.py -m "Closes issue #102 and refactors token caching"

# Enforce a specific type or scope
python main.py --type feat --scope auth

# Stage all modified and deleted tracked files first (like git commit -a)
python main.py -a

# Amend the previous commit with updated staged changes
python main.py --amend

# Non-interactive mode (auto-commits without confirmation prompt)
python main.py -y

# Use a different Gemini model
python main.py --model gemini-1.5-pro
```

### Handy Shell Alias
Add this alias to your `~/.bashrc` or `~/.zshrc`:
```bash
alias gca="python /path/to/agents/git-commit-agent/main.py"
```

---

## Example Input & Output

### 1. Staged change
```bash
git status -s
M src/auth/jwt.py
M src/auth/middleware.py
```

### 2. Output & Interactive Review
```text
Analysing staged changes with Google ADK (gemini-2.0-flash)...

================================================================
feat(auth): add token revocation check to JWT middleware

Validates incoming bearer tokens against the distributed redis blacklist
before forwarding requests to downstream route handlers.
================================================================

Use this commit message? [yes / no / edit / regenerate]: r
Enter instructions for regeneration (or press Enter for default): Mention Redis timeout fallback

Regenerating commit message with Google ADK...

================================================================
feat(auth): add JWT revocation check with Redis timeout fallback

Validates incoming bearer tokens against the distributed Redis blacklist.
Includes a fail-open timeout fallback to prevent auth deadlocks during
transient network partitions.
================================================================

Use this commit message? [yes / no / edit / regenerate]: y

✓ Commit created successfully!
[main a1b2c3d] feat(auth): add JWT revocation check with Redis timeout fallback
 2 files changed, 48 insertions(+), 6 deletions(-)
```

---

## How to Test

1. **Verify pre-flight git check:**
   Run from any non-git directory to confirm graceful error handling:
   ```bash
   (cd /tmp && python /path/to/agents/git-commit-agent/main.py)
   # Expected output: Error: Not a git repository...
   ```

2. **Verify dry-run execution:**
   Stage a sample change in any git repository:
   ```bash
   echo "test modification" >> README.md
   git add README.md
   python main.py --dry-run
   ```

3. **Verify secret scanner:**
   Stage a mock `.env` file or sensitive pattern and test detection:
   ```bash
   touch .env.test
   git add .env.test
   python main.py --dry-run
   # Expected output: Security warning banner showing sensitive file detected
   git rm --cached .env.test && rm .env.test
   ```

---

## Known Limitations

- Requires an active internet connection to contact Google AI Studio APIs.
- Very large diffs exceeding 25,000 characters are safely truncated to remain well within processing budgets.
- Rate limits on the Google AI Studio free tier apply; rapid consecutive requests may trigger `429 Too Many Requests`.

---

## Security & Privacy Considerations

- **Zero Committed Secrets**: Sensitive values are stored exclusively in `.env` or environment variables; `.env` is ignored by `.gitignore`.
- **Pre-flight Secret Scanning**: Checks diffs for credentials before sending payloads to the LLM API, helping prevent accidental data leakage.
- **Safe Subprocess Calls**: All Git actions use strict parameterized argument arrays rather than shell string execution.

---

## Future Improvements

- [x] Support `--amend` for revising existing commits.
- [x] Multi-turn regeneration with custom user feedback (`r` option).
- [x] Credential and secret scanning before API transmission.
- [x] Lockfile diff suppression for cleaner token utilization.
- [ ] Direct Git hook integration (`prepare-commit-msg`).
- [ ] Enterprise Vertex AI provider support alongside AI Studio.

---

## License

*Contributed under the project's open-source license.*
