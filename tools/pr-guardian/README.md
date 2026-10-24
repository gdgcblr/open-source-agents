# PR Guardian

> A Python command-line tool that reviews Git diffs for potential bugs, security risks, and maintainability issues using Google Gemini or a local mock reviewer.

## Overview

### Problem Statement & Intended Users

- **Problem:** Code changes can introduce risky patterns or maintenance issues that are easy to overlook during review. PR Guardian provides an additional, lightweight review of a supplied unified Git diff.

- **Intended Users:** Developers, students, open-source contributors, and engineering teams who want an initial review before human code review.

### Key Features

- **Diff-based review:** Reads a unified diff from a file without executing or modifying the reviewed code.

- **AI-assisted findings:** Gemini can return structured findings with severity, file, line when inferable, rationale, and a suggested fix.

- **Offline demo:** A local mock provider checks a small set of patterns without an API key.

- **JSON output:** Prints a structured report and can optionally save it to a file.

- **Input safeguards:** Applies input size limits and treats diff content as untrusted data.

PR Guardian is an assistant, not a comprehensive security scanner or a substitute for human review. It can miss issues and produce false positives.

## Technical Stack

- **Language & Runtime:** Python 3.10+

- **Agent Framework / Core Library:** Python CLI using the standard library and Google Gen AI SDK

- **Model:** Gemini model configured through `GEMINI_MODEL` or `--model`; the current code default is `gemini-3.8-flash`

- **External APIs / Tools:** Google Gemini API for AI-assisted reviews; Git for generating diffs

- **Dependencies:** `google-genai` (see `requirements.txt`)

## Architecture & Data Flow

PR Guardian reads a user-supplied unified diff, validates the input, and sends it to the selected provider. The mock provider applies simple pattern checks locally. The Gemini provider sends the diff to Google's API and parses the response into a structured report. The report is printed as JSON and may also be written to a file.

```text
Unified diff file
&#x20;      |
&#x20;      v
Input validation
&#x20;      |
&#x20;      v
Provider selection
&#x20;  /          \\
&#x20;Mock        Gemini API
&#x20;  \\          /
&#x20;      v
Structured JSON report
&#x20;      |
&#x20;      v
Terminal / optional output file
```

The tool does not post GitHub comments, apply suggested fixes, or execute code from the diff.

## Prerequisites

- Python 3.10 or newer

- `pip`

- For Gemini mode: a Google AI Studio API key and internet access

- For mock mode: no API key or network access is required

## Installation & Setup

From the repository root, navigate to the project directory:

```powershell
cd tools/pr-guardian
```

Create and activate a virtual environment on Windows PowerShell:

```powershell
py -3 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation, run `.venv\Scripts\python.exe` directly instead.

## Configuration & Environment Variables

The CLI reads environment variables directly; it does not automatically load `.env` or `.env.example`.

| Variable | Required | Default | Description |

| :--- | :--- | :--- | :--- |

| `GEMINI_API_KEY` | Only for Gemini | None | Google AI Studio API key |

| `GEMINI_MODEL` | No | `gemini-3.8-flash` in the current code | Gemini model identifier; can be overridden with `--model` |

Set the key in your current PowerShell session. Never commit real credentials:

```powershell
$env:GEMINI\_API\_KEY = "YOUR\_API\_KEY\_HERE"
```

Gemini usage may be subject to quotas or charges. Check your Google AI Studio account's current terms and limits.

## How to Run

### Offline demo

```powershell
python pr\_guardian.py --diff examples/sample.diff --provider mock
```

### AI review with Gemini

After setting `GEMINI_API_KEY`:

```powershell
python pr\_guardian.py --diff examples/sample.diff --provider gemini
```

### Automatic provider selection

The default `auto` mode uses Gemini when `GEMINI_API_KEY` is set and uses the mock provider otherwise:

```powershell
python pr\_guardian.py --diff examples/sample.diff
```

### Review a real Git diff

From the repository you want to review, generate a diff file:

```powershell
git diff main...HEAD -- . ':!\*.lock' | Set-Content -Encoding utf8 review.diff
```

Then run PR Guardian, adjusting the path to the location of your cloned repository:

```powershell
python path\\to\\open-source-agents\\tools\\pr-guardian\\pr\_guardian.py --diff review.diff --provider mock
```

For an existing diff file, save the report as JSON:

```powershell
python pr\_guardian.py --diff review.diff --provider gemini --output review.json
```

The report is printed to the terminal. When `--output` is provided, the JSON report is also saved to that file.

## Example Input & Output

### Example input

A unified Git diff containing this change:

```diff
\-    return total
\+    return eval("total")
```

### Example output

Illustrative output from a review of that change:

```json
{
&#x20; "summary": "The pull request replaces a direct variable return with an unnecessary call to eval().",
&#x20; "findings": \[
&#x20;   {
&#x20;     "severity": "medium",
&#x20;     "title": "Unnecessary use of eval",
&#x20;     "file": "app.py",
&#x20;     "line": 5,
&#x20;     "description": "The function returns eval(\\"total\\") instead of returning total directly.",
&#x20;     "suggestion": "Revert the change and return total directly."
&#x20;   }
&#x20; ],
&#x20; "provider": "gemini"
}
```

Actual wording and severity may vary between model responses.

## How to Test

Run the standard-library unit tests from the project directory:

```powershell
python -m unittest discover -s tests -v
```

The current test suite covers mock findings, report validation, JSON output, and added-line tracking across unified diff hunks. It does not require an API key.

A real Git diff was also tested locally with both mock and Gemini providers. Gemini availability depends on the model service and account quota.

## Known Limitations

- No GitHub integration; the tool reviews a diff supplied by the user.

- It does not build an AST or run language-specific linters or tests.

- Line numbers are best-effort for complex unified diffs.

- The mock provider checks only a few patterns and is intended for demonstrations.

- Gemini may return incorrect or incomplete findings or be temporarily unavailable.

- Prompt instructions are not a security boundary against prompt injection.

## Security & Privacy Considerations

- Diff contents sent to Gemini are transmitted to Google's API. Review diffs for secrets and confidential information before using Gemini.

- Never commit `.env` files, API keys, credentials, or private data.

- PR Guardian does not execute code from the diff or apply suggested fixes.

- Treat findings as suggestions; human review and appropriate security testing remain necessary.

## Future Improvements

- [ ] Add optional GitHub pull request integration.

- [ ] Improve diff parsing and line-number mapping for complex changes.

- [ ] Add configurable retry handling for transient API errors.

- [ ] Add more local checks and regression tests.

## License

This project is contributed under the repository's open-source license.
