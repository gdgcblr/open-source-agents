# diff-risk-reviewer

> A CLI agent that reads a `git diff`, summarises it in plain English, flags risks, and suggests tests, so reviewers catch problems before merge.

Built by [@naman0867](https://github.com/naman0867) for the GDG Cloud Bengaluru **FORK. BUILD. MERGE.** workshop (Road to DevFest 2026).

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Code review is slow and easy to rush. Risky changes (hard-coded secrets, migrations, auth changes, missing tests, leftover debug code) slip through when reviewers skim a large diff.
- **Intended Users**: Developers who want a quick self-review before opening a PR, reviewers who want a first-pass summary, and teams that want a simple CI gate.

### Key Features
- **Offline static checks**: Deterministic, no API key needed. Detects hard-coded secrets, sensitive files (migrations, CI/CD, auth, dependency manifests), source changes without tests, oversized diffs, and debug/TODO leftovers.
- **LLM review**: Gemini (default) or Grok adds a plain-English summary, extra risks that regexes cannot see, and suggested test cases.
- **Mock mode and CI support**: `--mock` runs with no API key, `--json` gives machine-readable output, and `--fail-on high|medium` exits with code 1 so it can gate a CI job.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: Vanilla Python script (`argparse`), `google-genai` SDK, and the `openai` SDK pointed at xAI's OpenAI-compatible endpoint
- **Models**: Gemini (default `gemini-3.8-flash`) or Grok (default `grok-4.20-reasoning`), both overridable
- **External APIs / Tools**: Google Gemini API, xAI API (optional), `python-dotenv`, `pytest` for tests

---

## Architecture & Data Flow

```
[git diff] --> [parse_diff] --> [static_checks] -----------------------+
                    |                                                  |
                    +--> [LLM review: Gemini / Grok / --mock] ---------+--> [merged report]
                                                                            (Markdown or JSON)
```

The diff is parsed into per-file added/removed lines. Static checks run first and always. The LLM review then receives the diff plus the static findings (so it does not repeat them) and returns JSON with a summary, extra risks, and suggested tests. Both result sets are merged and sorted by severity.

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.10 or newer
- `pip` (the virtual environment tool `venv` ships with Python)
- One API key, unless you use `--mock`: a free Gemini key from [Google AI Studio](https://aistudio.google.com/apikey), or an xAI key from [console.x.ai](https://console.x.ai) (requires credits)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/diff-risk-reviewer
   ```

2. **Set up the virtual environment / install dependencies:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Copy the example environment file and fill in your key:
   ```bash
   cp .env.example .env      # Windows: copy .env.example .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `LLM_PROVIDER` | No | `gemini` | LLM provider: `gemini` or `grok` |
| `GEMINI_API_KEY` | If provider is `gemini` | *None* | Gemini API key |
| `GEMINI_MODEL` | No | `gemini-3.8-flash` | Gemini model name |
| `XAI_API_KEY` | If provider is `grok` | *None* | xAI API key |
| `XAI_MODEL` | No | `grok-4.20-reasoning` | Grok model name (check xAI docs for current names) |

The `--mock` flag needs no variables at all.

---

## How to Run

```bash
# No API key needed: static checks only
python reviewer.py sample.diff --mock

# Real review of the bundled sample (Gemini by default)
python reviewer.py sample.diff

# Review your current changes
git diff | python reviewer.py -

# Review a branch against main
git diff main...HEAD | python reviewer.py -

# Use Grok instead of Gemini
git diff | python reviewer.py - --provider grok

# JSON output, and exit 1 if any high-severity risk is found (e.g. in CI)
git diff | python reviewer.py - --json --fail-on high
```

| Flag | Description |
| :--- | :--- |
| `--mock` | Skip the LLM and run static checks only |
| `--provider {gemini,grok}` | LLM provider (default: `$LLM_PROVIDER` or `gemini`) |
| `--model NAME` | Override the model for the chosen provider |
| `--json` | Machine-readable output |
| `--fail-on {high,medium}` | Exit with code 1 at or above this severity |

---

## Example Input & Output

### Example Input

`python reviewer.py sample.diff`, where [`sample.diff`](sample.diff) contains:

```diff
diff --git a/app/auth/login.py b/app/auth/login.py
index 1a2b3c4..5d6e7f8 100644
--- a/app/auth/login.py
+++ b/app/auth/login.py
@@ -1,6 +1,12 @@
 import hashlib
 
+API_KEY = "demo-placeholder-value-1234"
+
 def check_password(user, password):
-    return user.hash == hashlib.md5(password.encode()).hexdigest()
+    # TODO: switch to bcrypt
+    print("checking", user.name)
+    breakpoint()
+    return user.hash == hashlib.sha256(password.encode()).hexdigest()
diff --git a/migrations/0007_add_last_login.sql b/migrations/0007_add_last_login.sql
new file mode 100644
--- /dev/null
+++ b/migrations/0007_add_last_login.sql
@@ -0,0 +1,2 @@
+ALTER TABLE users ADD COLUMN last_login TIMESTAMP;
+UPDATE users SET last_login = NOW();
```

### Example Output

A genuine run using Gemini (`gemini-3.8-flash`). The LLM adds risks the static checks cannot see (the hashing change and the migration lock), and its exact wording varies between runs:

```markdown
# Diff Risk Report (2 files, +8/-1)

## Summary
This change updates password verification from MD5 to unsalted SHA-256 in the authentication module and introduces a migration adding a `last_login` column. The hashing algorithm switch will break authentication for all existing users whose stored hashes are in MD5 format. Additionally, the database migration performs an immediate full-table update that could cause table lock contention on large production datasets.

## Risks
- **[HIGH]** Possible secret: Hard-coded credential assignment: app/auth/login.py (value redacted)
- **[HIGH]** Breaking change in password verification algorithm: Switching from MD5 to SHA-256 without a legacy fallback or migration path will cause verification to fail for all existing users whose passwords are stored as MD5 hashes.
- **[MEDIUM]** Sensitive file touched: Authentication-related code: app/auth/login.py
- **[MEDIUM]** Sensitive file touched: Database migration: migrations/0007_add_last_login.sql
- **[MEDIUM]** Source changed without tests: app/auth/login.py
- **[MEDIUM]** Use of unsalted fast hash for passwords: SHA-256 without salting or key stretching is vulnerable to brute-force and rainbow table attacks; a dedicated password hashing algorithm such as bcrypt, Argon2, or PBKDF2 should be implemented.
- **[LOW]** Debug/TODO leftovers: app/auth/login.py: 2 line(s), e.g. `# TODO: switch to bcrypt`
- **[LOW]** Unbounded mass update in migration: Executing `UPDATE users SET last_login = NOW();` without batching locks the `users` table on large databases and inaccurate historical data is written by setting all inactive accounts to the current timestamp.

## Suggested tests
- Verify that existing users with MD5 hashes can still authenticate or are prompted/migrated appropriately.
- Verify password verification succeeds for newly created accounts using the updated hashing method.
- Verify that authentication requests complete successfully without hanging or halting execution.
- Benchmark migration 0007 against a staging database with realistic user volume to assess table lock duration.
```

---

## How to Test

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

9 tests cover diff parsing, secret detection, risky-file and missing-test detection, mock mode, JSON-fence parsing, missing-key handling, and the `--fail-on` exit code. None of them need an API key.

For a manual check without any key:

```bash
python reviewer.py sample.diff --mock    # should print a report with HIGH, MEDIUM and LOW findings
```

---

## Known Limitations

- Static checks are regex heuristics, so expect false positives and false negatives. They are not a substitute for a real secret scanner or human review.
- The LLM sees only the diff (truncated to 60,000 characters), not the rest of the codebase.
- LLM output can be wrong or miss issues. Treat it as a second pair of eyes, and wording varies between runs.
- Model names change over time. If you get a "model not found" error, set `GEMINI_MODEL` or `XAI_MODEL` to a current name.
- Each LLM run makes one API call, so check your provider's quota and pricing (xAI requires paid credits; Gemini free tier has rate limits).
- Live Gemini run tested on Windows (PowerShell, Python 3.10). Unit tests also pass on Linux (Python 3.12). macOS is untested.
- The Grok provider is implemented but has not been run against the live xAI API.

---

## Security & Privacy Considerations

- **Secrets Handling**: API keys are read from environment variables or a local `.env` file, which is git-ignored. Only placeholders live in `.env.example`. Detected secrets are reported with the value redacted.
- **Data Privacy**: In LLM mode, the diff (up to 60,000 characters) is sent to the chosen provider (Google or xAI). Do not run it on code you are not allowed to share. `--mock` sends nothing anywhere.
- **Safety**: The tool is read-only. It never executes code or shell commands from the diff, and it makes no changes to your repository.

---

## Future Improvements

- [ ] Support local models via Ollama for fully private reviews.
- [ ] Add a GitHub Action that comments the report on pull requests.
- [ ] Add more static checks (disabled SSL verification, wildcard CORS, insecure deserialization).
- [ ] Review large diffs in chunks instead of truncating.

---

## License

*This project is contributed under the repository's open-source license (MIT).*
