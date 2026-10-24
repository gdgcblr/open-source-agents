# DevGuard

> A lightweight, local-first CLI that enforces command permission policies deterministically, maintains structured audit history, diagnoses command failures, and generates conventional commit messages and pull request descriptions.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Modern developer workflows and autonomous AI coding tools frequently execute terminal commands. Running unverified shell commands risks accidental repository corruption (e.g., unintended hard resets, destructive cleans, forced pushes). Developers need an auditable, deterministic gatekeeper that intercepts routine commands without cumbersome overhead.
- **Intended Users**: Software engineers, open-source contributors, and teams seeking lightweight, reproducible command-policy enforcement, failure diagnostics, and automated Git documentation.

### Key Features
1. **Stronger Command Permissions & Explanations (`devguard run`, `devguard policy explain`)**:
   - Matches discrete argument tokens with path normalization.
   - Prevents deceptive executable names (`git-malicious`) from matching genuine rules.
   - Forbids broad single-token allow rules on multi-command tools (`git`, `python`, `npm`, `uv`, `bash`).
   - Detailed rule explanations with specificity scores and candidate evaluation logs.
2. **Interactive Approval & Audit History (`devguard history`)**:
   - Displays full executable, resolved path, and arguments before asking for user approval.
   - Non-interactive environments fail safely (no silent execution).
   - Structured JSONL audit log (`.devguard/history.jsonl`) with automated secret redaction (API keys, tokens, DB URLs) and automatic line rotation.
3. **Reusable Policy Presets (`devguard preset list`, `devguard preset show`)**:
   - Built-in presets: `conservative` (fail-closed, read-only Git allowed), `development` (balanced read-only Git + testing allowed), and `custom`.
   - Preserves authoritative deny precedence: user rules can never override preset `deny` rules.
4. **Improved AI Commit Assistant (`devguard commit-message`)**:
   - Inspects staged Git diff only; immediate zero-cost exit on empty diffs.
   - Supports scopes (`--scope`) and candidate generation (`--candidates 1-5`).
   - Redacts credentials from diffs before sending to model.
   - Clearly labels offline deterministic fallbacks (`[Fallback (Deterministic)]`).
5. **Build and Test Failure Diagnosis (`devguard diagnose`)**:
   - Always evaluates policy first; never executes denied commands.
   - Extracts traceback file:line locations and error lines.
   - Separates verified evidence from AI hypotheses and potential fixes.
   - Includes safety disclaimers against unverified recommendations.
6. **Pull-Request Description Generator (`devguard pr-description`)**:
   - Generates conventional Markdown PR descriptions from branch diff and commit history.
   - Highlights locally verified test executions from DevGuard's audit history separately from suggested tests.
   - Can optionally export Markdown directly to disk (`-o PR.md`).

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
  ├── init           ──► Creates devguard.yaml (supports --preset)
  ├── policy explain ──► Explains rule matching, specificity, and source
  ├── run -- <cmd>   ──► [Policy Engine] ──► [Approval Prompt (if ask)] ──► [Safe Subprocess Runner]
  │                                                                            │
  │                                                                            ▼
  │                                                                   [Audit Logger (.devguard/)]
  ├── history        ──► Inspects recent audit records and secret redaction
  ├── preset         ──► Lists and displays built-in policy presets
  ├── commit-message ──► [Git Staged Diff] ──► [Secret Redactor] ──► [Gemini AI / Fallback]
  ├── diagnose       ──► [Policy Check] ──► [Execute] ──► [Error Extraction] ──► [Structured Report]
  └── pr-description ──► [Git Branch Context] ──► [Audit History] ──► [Structured PR Markdown]
```

---

## Prerequisites

- Python 3.10 or higher
- Git 2.20 or higher
- (Optional) Google Gemini API Key (only needed for AI commit messages, failure diagnosis, and PR descriptions; policy enforcement functions 100% offline).

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
   # Core CLI and permission manager:
   pip install -e .

   # Development and test dependencies:
   pip install -e ".[dev]"

   # Optional AI provider dependencies (for Gemini features):
   pip install -e ".[ai]"
   ```

4. **Configure Environment Variables (Optional):**
   ```bash
   cp .env.example .env
   # Add your GEMINI_API_KEY to .env (or export GEMINI_API_KEY="...")
   ```

---

## How to Run

### 1. Reusable Policy Presets
```bash
# List available presets:
devguard preset list

# Inspect detailed rules and trade-offs of a preset:
devguard preset show conservative
devguard preset show development

# Initialize a project configuration using a preset:
devguard init --preset development
```

### 2. Inspect Policy Decisions
```bash
# Explain how policy evaluates a command without running it:
devguard policy explain -- git status -s
devguard policy explain -- git reset --hard
```

### 3. Run Commands Through Policy Manager
```bash
# Allowed command (runs directly):
devguard run -- git status

# Denied command (refused with exit code 1):
devguard run -- git reset --hard

# Prompted command (requires interactive user confirmation):
devguard run -- git commit -m "feat: initial commit"

# In CI / Non-interactive environments:
devguard run --non-interactive -- git commit -m "msg"  # fails safely
```

### 4. Inspect Execution History & Audit Logs
```bash
# View recent execution records in formatted table:
devguard history

# View raw audit records with secret redaction as JSON:
devguard history --json --limit 5
```

### 5. Generate Commit Messages
```bash
# Stage changes:
git add src/devguard/policy.py

# Generate AI conventional commit message:
devguard commit-message

# Generate with explicit scope and multiple candidates:
devguard commit-message --scope policy --candidates 3

# Force deterministic offline fallback:
devguard commit-message --fallback
```

### 6. Build and Test Failure Diagnosis
```bash
# Supervised execution and automated diagnosis of failures:
devguard diagnose -- python3 -m pytest

# Run offline deterministic diagnosis:
devguard diagnose --fallback -- pytest
```

### 7. Pull Request Description Generation
```bash
# Generate Markdown description from branch diff:
devguard pr-description

# Compare against a specific base and save to file:
devguard pr-description --base main --output PR.md
```

---

## How to Test

Run the full automated test suite using pytest:

```bash
cd tools/devguard
source .venv/bin/activate
pytest tests/ -v
```

The 80-test suite covers:
- Structured argument matching, path normalization, and deceptive name defenses (`test_policy_explain.py`, `test_policy.py`).
- Precedence resolution (longest prefix wins, DENY > ASK > ALLOW).
- Non-interactive fail-safe and interactive approval rejection (`test_audit.py`).
- Audit log persistence, line rotation, and secret redaction (`test_audit.py`).
- Built-in presets and authoritative deny inheritance (`test_presets.py`).
- Staged-only git diff, binary file handling, scopes, candidates, and AI fallback (`test_commit_message.py`).
- Failure diagnosis: traceback extraction, error parsing, evidence vs hypothesis separation (`test_diagnose.py`).
- PR description generation with verified audit test tracking (`test_pr_description.py`).
- CLI commands and options via Click's test runner (`test_cli.py`).

---

## Security & Privacy Considerations

- **No Shell Execution**: DevGuard strictly avoids `shell=True` in subprocess calls. Commands are passed directly as argument arrays, eliminating shell metacharacter and string injection risks.
- **Structured Matching**: Prefix matching evaluates discrete argument tokens rather than string prefixes, preventing commands like `git-malicious` from matching a `git` rule.
- **Secret Redaction**: Common credentials (Bearer tokens, Authorization headers, Google API keys, OpenAI keys, GitHub/GitLab PATs, DB URIs) are redacted prior to persistent audit logging or external AI requests.
- **Redaction Disclaimer**: Secret redaction uses heuristic regex patterns and cannot guarantee 100% elimination of all custom or obfuscated secrets.
- **Application Gateway Limitation**: DevGuard operates as an application-level CLI gateway. It intercepts commands invoked through `devguard run`. It does not restrict subprocesses spawned by allowed programs or prevent users from running unsanctioned binaries outside the CLI wrapper.

---

## License

This project is contributed under the repository's [MIT License](../../LICENSE) &copy; 2026 GDG Cloud Bengaluru Community.
