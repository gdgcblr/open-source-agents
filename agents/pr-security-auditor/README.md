# PR Security Auditor

> A semi-autonomous reviewer that combines local security checks, current vulnerability lookups, and a Google Gemini review of Git changes.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Security issues such as committed credentials, unsafe code patterns, and vulnerable dependencies can slip into a change before review.
- **Intended Users**: Contributors and maintainers reviewing staged work, working-tree changes, or a branch against a base ref.

### Key Features
- Scans added diff lines for common credential formats and secret assignments, without copying secret values into the report.
- Flags a small set of recognizable risky code patterns, including dynamic evaluation, unsafe deserialization, disabled TLS verification, and obvious interpolated SQL.
- Checks exact versions in changed `requirements.txt` and `package.json` files against the OSV vulnerability database.
- Requires a Google Gemini model review with Google Search grounding for code quality and current public vulnerability information.
- Includes up to three suggested remediations and cited sources per finding; it never applies fixes automatically.
- Writes a concise Markdown report and returns a nonzero status when findings or audit errors need attention.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: Standalone Python CLI; deterministic local checks followed by required LLM review.
- **Models**: `gemini-3.8-flash` through the Gemini Interactions API by default.
- **External APIs / Tools**: Git CLI; OSV vulnerability API; Gemini Interactions API with Google Search grounding.

---

## Architecture & Data Flow

The CLI obtains a unified Git diff and changed-file list, runs local secret and risky-code checks, queries OSV for exact dependency versions, then requires a Gemini review with Google Search grounding for current public security information. Eligible added code lines are sent to Google for review after local filtering. The LLM provides code-quality/security findings, suggested fixes, and citations; it does not execute or modify code.

```text
Git diff --> Local secret/code checks -----------------------------+
    |                                                             |
Changed manifests --> Exact versions --> OSV ---------------------+--> Markdown report
    +--> Filtered added lines + dependency context --> Gemini API    |
                                                  + Google Search ----+
```

---

## Prerequisites

- Python 3.10+
- Git available on `PATH`
- Network access to OSV and the Gemini API is required for every complete scan.
- A Gemini API key is required for every scan.

---

## Installation & Setup

From the repository root:

```bash
python -m pip install -e agents/pr-security-auditor
```

The project uses only the Python standard library. Create a key in [Google AI Studio](https://aistudio.google.com/apikey) and configure `GEMINI_API_KEY` before running the auditor.

---

## Configuration & Environment Variables

Gemini credentials and model selection are read from environment variables; `.env.example` is a reference and is not automatically loaded. A scan without the key is incomplete and returns a nonzero exit status.

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes | None | Gemini API key. Never commit the real key. |
| `GEMINI_MODEL` | No | `gemini-3.8-flash` | Gemini model name for the required review. |

Set the key in the current PowerShell session on Windows:

```powershell
$env:GEMINI_API_KEY = "your_gemini_api_key_here"
```

On Linux/macOS:

```bash
export GEMINI_API_KEY="your_gemini_api_key_here"
```

---

## How to Run

Run in a Git repository:

```bash
pr-security-auditor
```

By default, the auditor checks tracked changes relative to `HEAD` (including staged and unstaged changes) and writes `security-audit.md` in the current directory. Review only staged changes:

```bash
pr-security-auditor --staged
```

Compare the working tree with a base branch:

```bash
pr-security-auditor --base origin/main --output reports/security-audit.md
```

Every scan runs the Gemini review through the Interactions API with Google Search grounding using `gemini-3.8-flash` by default. Set `GEMINI_MODEL` to another supported Gemini model name if desired. There is no offline mode for a complete audit; if a required external check fails, the report marks the audit incomplete and the CLI exits with status `2`.

Gemini API pricing and free-tier limits can change; check the current [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) and [Google Search grounding documentation](https://ai.google.dev/gemini-api/docs/google-search) before running scans.

Exit codes: `0` means no findings or audit errors; `1` means findings were reported; `2` means the audit could not be completed cleanly. A report is still written when possible if a check fails.

---

## Example Input & Output

### Example Input

```bash
pr-security-auditor --staged
```

Local checks run first. Added lines matching local secret patterns and lines over 1,000 characters are excluded from the hosted review. Common email addresses, phone numbers, street addresses, names in common fields, and capitalized full-name-like text are masked before submission. File paths are replaced with temporary aliases in model context and mapped back for findings. These PII checks are heuristic: they may miss names in unusual formats and may mask benign proper names. The model uses Google Search grounding to find current public vulnerability information. Reports include up to three suggested fix options and verified Google Search citations where applicable.

### Example Output

```markdown
# Security Audit Report

Status: Findings require review

## Summary
- Findings: 1
- Audit errors: 0

## Findings

| Severity | Type | Location | Finding | Suggested fixes | Sources |
| --- | --- | --- | --- | --- | --- |
| HIGH | Secret | `src/config.py:18` | Possible hardcoded credential (value redacted). | Revoke and rotate the credential; load it from a secret manager or environment. | — |
```

---

## How to Test

From this directory:

```bash
python -m unittest discover -s tests -v
```

Tests use mocked OSV/Gemini responses and temporary directories; they do not require network access.

---

## Design & Task List

- [Design](DESIGN.md): architecture, data flow, boundaries, and testing strategy.
- [Task list](TASKS.md): MVP verification and prioritized follow-up work.

---

## Known Limitations

- Pattern matching is heuristic: it can miss secrets or flag harmless examples. Findings require human review.
- Only added diff lines are checked for secret and code patterns.
- Dependency checks support exact versions in `requirements.txt` and `package.json`; ranges, lockfiles, other manifest formats, and transitive dependency resolution are not evaluated.
- OSV/Gemini availability, Google Search coverage, and advisory publication delays affect results. A failed mandatory check makes the audit incomplete.
- The required hosted LLM review sends eligible added code lines to the Gemini API. Local secret-pattern filtering is heuristic and cannot guarantee that all sensitive data is removed.
- Before hosted review, the auditor masks common email, phone, and street-address formats, names in common fields and title-cased full-name-like text, and anonymizes file paths. This is heuristic PII filtering, not a guarantee; it may miss unusual formats or mask benign text. Review changes before running scans and do not submit data you are not permitted to share.
- Current vulnerability results are based on Google Search citations returned during the scan, not a guarantee that every newly published advisory was found.
- Model findings can be inaccurate or influenced by prompt-like text in code. Treat them as suggestions and verify each finding.
- The tool does not execute code, change files, or automatically fix findings.

---

## Security & Privacy Considerations

- Deterministic pattern scanning happens locally. The auditor does not execute project code or shell commands from the diff.
- OSV receives only package ecosystem, package name, and exact version. Source code, paths, and credentials are not sent.
- The Gemini API receives eligible added code lines and dependency metadata on every scan. Lines matching local secret patterns and oversized lines are excluded, but pattern-based filtering is not infallible. Review Google's current data policies and do not use this hosted workflow for code you are not permitted to share. Google states content submitted through unpaid services may be used to improve its products; avoid sending private or sensitive source code through the free tier.
- Secret values are redacted from findings and reports. Review the report before sharing it because filenames and advisory details may still be sensitive.
- A clean report is not proof that a change is secure; use it as one input to human review.

---

## Future Improvements

- [ ] Add lockfile-aware transitive dependency checks.
- [ ] Support additional package ecosystems and manifest formats.
- [ ] Add an opt-in Git pre-commit hook example.

---

## License

This project is contributed under the repository's open-source license.
