# DevGuard

> A lightweight, local-first CLI that enforces command permission policies deterministically and generates conventional commit messages.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Modern developer workflows and AI coding tools frequently trigger or suggest shell commands. Running unverified terminal commands risks accidental system state corruption (e.g., unintended hard resets, destructive cleans, forced pushes). Developers need an auditable, deterministic gatekeeper that intercepts routine commands without cumbersome overhead.
- **Intended Users**: Software engineers, open-source contributors, and teams seeking lightweight, reproducible command-policy enforcement and automated Git commit message formatting.

### Key Features
- **Deterministic Command Policy Enforcement**: Evaluates commands against structured prefix rules with three explicit decisions: `allow`, `ask`, and `deny`.
- **Strict Precedence & Fail-Closed Defaults**: Longest prefix match wins; explicit `deny` rules always beat `allow` at identical specificity; unmatched commands default to deny/ask.
- **Safe Subprocess Execution**: Direct execution via `subprocess.run(shell=False)` with structured argument lists, preventing shell injection vulnerabilities.
- **AI-Assisted & Fallback Conventional Commit Messages**: Inspects staged changes (`git diff --staged`) and produces clean conventional commit messages via Google Gemini (with an offline deterministic fallback).

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **CLI Framework**: Click (>=8.0.0)
- **Configuration Format**: YAML (PyYAML >=6.0)
- **Models / AI Provider**: Google Gemini 2.5 Flash via `google-genai` (optional, lazy-loaded)
- **Testing**: pytest (>=7.0.0)

---

## Architecture & Data Flow

```
[User Terminal]
       │
       ▼
 [devguard CLI]
  ├── init           ──► Generates devguard.yaml configuration
  ├── run -- <cmd>   ──► [Policy Engine] ──(Structured Prefix Match)──► [Decisions: allow/ask/deny]
  │                                                                            │
  │                                                                (allow / user confirmed)
  │                                                                            ▼
  │                                                                  [Safe Subprocess Runner]
  └── commit-message ──► [Git Staged Diff] ──► [Gemini AI / Fallback] ──► [Conventional Commit]
```

### Policy Precedence Rules
1. **Structured Tuple Matching**: Commands are evaluated as argument tuples (`["git", "status"]`), never raw string prefixes.
2. **Specificity First**: Longest matching rule wins (e.g., `["git", "reset", "--hard"]` overrides `["git", "reset"]`).
3. **Explicit Deny Priority**: At identical prefix lengths, `deny > ask > allow`.
4. **Fail-Closed Fallback**: Commands with no matching rule default to the configured `default_policy` (or deny).

---

## Prerequisites

- Python 3.10 or higher
- Git 2.20 or higher
- (Optional) Google Gemini API Key (only needed for AI-assisted commit messages; the permission manager functions entirely offline)

---

## Installation & Setup

1. **Navigate to the tool directory:**
   ```bash
   cd tools/devguard
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate    # On Windows: .venv\Scripts\activate
   ```

3. **Install the package:**
   ```bash
   # Core installation (CLI and permission manager):
   pip install -e .

   # Development & testing dependencies:
   pip install -e ".[dev]"

   # Optional AI provider dependencies (for Gemini commit messages):
   pip install -e ".[ai]"
   ```

4. **Configure Environment Variables (Optional):**
   ```bash
   cp .env.example .env
   # Edit .env and set your GEMINI_API_KEY
   ```

---

## Configuration & Environment Variables

### Policy Configuration (`devguard.yaml`)

Initialize a default configuration in your workspace:
```bash
devguard init
```

Example `devguard.yaml`:
```yaml
default_policy: ask

allow:
  - ["git", "status"]
  - ["git", "diff"]
  - ["git", "log"]
  - ["python3", "-m", "pytest"]
  - ["echo"]

ask:
  - ["git", "commit"]
  - ["git", "push"]

deny:
  - ["git", "reset", "--hard"]
  - ["git", "clean", "-fdx"]
```

### Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | No | *None* | Google Gemini API key for AI-assisted commit messages. |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Gemini model identifier. |

---

## How to Run

### 1. Initialize Configuration
```bash
devguard init
# Or overwrite an existing config:
devguard init --force
```

### 2. Run Commands Through Policy Manager
```bash
# Allowed command (runs directly):
devguard run -- git status

# Denied command (refused with exit code 1):
devguard run -- git reset --hard

# Prompted command (requires user confirmation):
devguard run -- git commit -m "feat: initial commit"
```

### 3. Generate Commit Messages
```bash
# Stage your changes:
git add src/devguard/policy.py

# Generate message using Gemini (or automatic fallback if offline):
devguard commit-message

# Or force deterministic offline fallback generation:
devguard commit-message --fallback
```

---

## Example Input & Output

### Example: Allowed Command
```
$ devguard run -- git status
✓ [ALLOWED] git status
  Reason: Allowed by rule: [git status]
On branch feat/devguard
nothing to commit, working tree clean
```

### Example: Denied Command
```
$ devguard run -- git reset --hard HEAD~1
✖ [DENIED] git reset --hard HEAD~1
  Reason: Explicitly denied by rule: [git reset --hard]
```

### Example: AI Commit Message Generation
```
$ devguard commit-message
============================================================
Proposed Commit Message:
============================================================

feat(policy): implement structured prefix matching and precedence logic

============================================================
Copy the message above or run: git commit -m "..."
```

---

## How to Test

Run the full automated test suite using pytest:

```bash
cd tools/devguard
source .venv/bin/activate
pytest tests/ -v
```

The test suite covers:
- Rule loading, schema validation, and malformed configuration handling (`test_config.py`).
- Deterministic prefix matching, specificity ranking, and precedence resolution (`test_policy.py`).
- Safe subprocess execution and error isolation without shell execution (`test_runner.py`).
- Conventional commit message heuristics and AI fallback mechanics (`test_commit_message.py`).
- CLI command invocation, flag handling, and exit codes via Click's test harness (`test_cli.py`).

---

## Known Limitations

- **Not an Operating System Sandbox**: DevGuard operates as an application-level CLI gateway. It intercepts commands invoked through `devguard run`. It does not restrict subprocesses spawned by allowed programs or prevent users from running unsanctioned binaries outside the CLI wrapper.
- **Git Repository Requirement**: The `commit-message` command requires being run within an initialized Git repository with staged changes.
- **API Connectivity**: AI commit message generation requires network access to the Google Gemini API. If the API is unreachable, DevGuard automatically falls back to deterministic rule-based generation.

---

## Security & Privacy Considerations

- **No Shell Execution**: DevGuard strictly avoids `shell=True` in subprocess calls. Commands are passed directly as argument arrays, eliminating shell metacharacter and string injection risks.
- **Structured Matching**: Prefix matching evaluates discrete argument tokens rather than string prefixes, preventing commands like `git-malicious` from matching a `git` rule.
- **Zero Committed Secrets**: API keys are read strictly from environment variables or local `.env` files, which are gitignored by default.
- **Local-First**: The policy engine executes 100% locally with zero external network calls.

---

## Future Improvements

- [ ] Support wildcard argument patterns in policy rules (e.g., `["npm", "run", "*"]`).
- [ ] Add pre-commit hook integration (`devguard install-hook`).
- [ ] Support local LLM backends (e.g., Ollama / llama.cpp) for commit message generation.
- [ ] Add command execution audit logging to a structured JSON-lines file.

---

## License

This project is contributed under the repository's [MIT License](../../LICENSE) &copy; 2026 GDG Cloud Bengaluru Community.

