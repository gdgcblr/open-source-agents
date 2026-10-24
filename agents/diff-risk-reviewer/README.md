# diff-risk-reviewer

A small CLI agent that reads a `git diff`, summarises it in plain English, flags risks, and suggests tests.

> Part of **FORK. BUILD. MERGE.** (GDG Cloud Bengaluru, Road to DevFest 2026).

## Overview

Code review is slow and easy to rush. `diff-risk-reviewer` combines two layers:

1. **Static checks** (offline, deterministic): hard-coded secrets, sensitive files (migrations, CI, auth, dependency manifests), source changes without tests, oversized changes, and debug/TODO leftovers.
2. **LLM review** (Gemini or Grok, your choice): a short summary and suggested test cases. Use `--mock` to skip this layer, so no API key is needed.

## Tech stack

- Python 3.10+
- [`google-genai`](https://pypi.org/project/google-genai/) SDK (Gemini)
- [`openai`](https://pypi.org/project/openai/) SDK pointed at xAI's OpenAI-compatible endpoint (Grok)
- `python-dotenv` (optional, loads `.env`)
- `pytest` for tests

## Prerequisites

- Python 3.10 or newer
- One API key (not needed with `--mock`): a free Gemini key from [Google AI Studio](https://aistudio.google.com/apikey), or an xAI key from [console.x.ai](https://console.x.ai) (requires credits)

## Setup

```bash
cd agents/diff-risk-reviewer
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then put your key in .env and set LLM_PROVIDER
```

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | No | `gemini` (default) or `grok` |
| `GEMINI_API_KEY` | If provider is gemini | Gemini API key |
| `GEMINI_MODEL` | No | Default `gemini-3.8-flash` |
| `XAI_API_KEY` | If provider is grok | xAI API key |
| `XAI_MODEL` | No | Default `grok-4.20-reasoning` (check xAI docs for current names) |

## Usage

```bash
# No API key needed
python reviewer.py sample.diff --mock

# Real review of your current changes (Gemini by default)
git diff | python reviewer.py -

# Use Grok instead
git diff | python reviewer.py - --provider grok

# Review a branch against main
git diff main...HEAD | python reviewer.py -

# JSON output, and fail (exit 1) if any high-severity risk is found, e.g. in CI
git diff | python reviewer.py - --json --fail-on high
```

| Flag | Description |
|---|---|
| `--mock` | Skip the LLM; run static checks only |
| `--provider {gemini,grok}` | LLM provider (default: `$LLM_PROVIDER` or `gemini`) |
| `--model NAME` | Override the model for the chosen provider |
| `--json` | Machine-readable output |
| `--fail-on {high,medium}` | Exit with code 1 at or above this severity |

## Example

Input: [`sample.diff`](sample.diff). Output of `python reviewer.py sample.diff --mock` (a genuine run):

```markdown
# Diff Risk Report (2 files, +8/-1)

## Summary
[mock] 2 file(s) changed (+8/-1): app/auth/login.py, migrations/0007_add_last_login.sql

## Risks
- **[HIGH]** Possible secret: Hard-coded credential assignment: app/auth/login.py (value redacted)
- **[MEDIUM]** Sensitive file touched: Authentication-related code: app/auth/login.py
- **[MEDIUM]** Sensitive file touched: Database migration: migrations/0007_add_last_login.sql
- **[MEDIUM]** Source changed without tests: app/auth/login.py
- **[LOW]** Debug/TODO leftovers: app/auth/login.py: 2 line(s), e.g. `# TODO: switch to bcrypt`

## Suggested tests
- [mock] Run with a real model (omit --mock) for test suggestions.
```

### Example with a real model

Output of `python reviewer.py sample.diff` using Gemini (`gemini-3.8-flash`), a genuine run. Note that the LLM adds risks the static checks cannot see (the hashing change and the migration lock), and the exact wording will vary between runs:

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

## Testing

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

9 tests cover diff parsing, secret detection, risky-file and missing-test detection, mock mode, JSON-fence parsing, missing-key handling, and the `--fail-on` exit code. None require an API key.

## How it works

```
git diff -> parse_diff -> static_checks ----------\
                      \-> Gemini (or --mock) -----+-> merged report (Markdown / JSON)
```

## Known limitations

- Static checks are regex heuristics: expect false positives and false negatives. They are not a substitute for a real secret scanner or human review.
- Grok/Gemini model names change over time; if you get a "model not found" error, set `XAI_MODEL` / `GEMINI_MODEL` to a current name.
- The LLM sees only the diff (truncated to 60,000 characters), not the rest of the codebase.
- LLM output can be wrong or miss issues. Treat it as a second pair of eyes.
- The diff is sent to the chosen provider's API (Google or xAI). Do not use it on code you are not allowed to share.
- Each LLM run makes one API call; check your provider's quota and pricing (xAI requires paid credits).
- Live Gemini run tested on Windows (PowerShell, Python 3.10). Unit tests also pass on Linux (Python 3.12). macOS untested. The Grok provider path is implemented but has not been run against the live xAI API.

## License

MIT, same as the parent repository.
