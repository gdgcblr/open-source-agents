# Code Review Agent

> A Google ADK-powered assistant that reviews source code for likely bugs, security risks, performance issues, and maintainability problems.

---

## Overview

### Problem Statement & Intended Users

- **Problem:** Manual code reviews can miss defects or take time to produce consistent, actionable feedback.
- **Intended Users:** Developers, students, maintainers, and teams who want a first-pass review before human review or testing.

### Key Features

- Reviews pasted code snippets and explains actionable findings.
- Can read supported source-code files inside the current working directory.
- Classifies findings as Critical, High, Medium, or Low and suggests practical fixes.
- Includes tests for the file-reading tool and its path/size restrictions.
- Does not execute code, run shell commands, or modify source files.

---

## Technical Stack

- **Language & Runtime:** Python 3.10+
- **Agent Framework / Core Library:** Google Agent Development Kit (ADK)
- **Model:** Gemini model configured by `MODEL_NAME` (default: `gemini-2.5-flash`)
- **External APIs / Tools:** Google AI API through ADK; local, read-only source-file reader

---

## Architecture & Data Flow

```text
User's code or relative file path
            |
            v
Google ADK Code Review Agent
            |
            +----> Optional read_source_file tool
            |       (path and size checks; read only)
            |
            v
LLM analysis and severity classification
            |
            v
Findings, explanations, fixes, and suggested tests
```

The model's findings are suggestions and must be validated by a developer. The agent does not execute or change reviewed code.

---

## Prerequisites

- Python 3.10 or newer
- pip
- A Google AI Studio API key, unless you configure another supported Google ADK model provider
- Git (only if contributing through a Git branch and pull request)

---

## Installation & Setup

From the repository root:

```powershell
cd agents/code-review-agent
python -m venv .venv
```

Activate the environment on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use Command Prompt instead:

```cmd
.venv\Scripts\activate.bat
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create a local environment file:

```powershell
Copy-Item .env.example .env
```

Open `.env` and replace the placeholder `GOOGLE_API_KEY` with your own key. Keep `.env` private and never commit it.

---

## Configuration & Environment Variables

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | Yes for Google AI Studio | None | Google AI Studio API key |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | `FALSE` | Set to `TRUE` when intentionally configuring Vertex AI credentials and project settings |
| `MODEL_NAME` | No | `gemini-2.5-flash` | ADK model identifier |

Do not put real credentials in `.env.example` or source files. Model availability, access, and pricing depend on your Google account and provider configuration.

---

## How to Run

Run the ADK terminal chat from this directory's parent folder:

```powershell
cd .. 
adk run code-review-agent
```

Or launch the local ADK development UI:

```powershell
adk web
```

Then select `code-review-agent` in the UI. Use the UI only for local development; do not expose it to an untrusted network.

### Example prompts

Paste a snippet:

```text
Review this Python code for correctness, security, and edge cases:

def get_user(users, user_id):
    for user in users:
        if user["id"] == user_id:
            return user
```

Review a file relative to the current working directory:

```text
Read and review src/example.py for bugs and security issues.
```

The file reader accepts supported source-code extensions only, requires a relative path inside the current working directory, and limits files to 100,000 bytes.

---

## Example Input & Output

### Example Input

```python
def divide(a, b):
    return a / b
```

### Illustrative Output

```text
Finding 1
Severity: Medium
Location: divide() — exact line depends on the submitted snippet
Issue: The function raises ZeroDivisionError when b is zero.
Why it matters: A zero divisor can interrupt the caller's workflow.
Suggested fix: Validate b before dividing or handle ZeroDivisionError.
Suggested test: Verify normal division and the zero-divisor case.

Summary
Add an explicit policy for a zero divisor. This is an illustrative example,
not a record of a live model run.
```

Actual findings depend on the submitted code and model response. The agent may miss defects or produce false positives.

---

## How to Test

From `agents/code-review-agent` with the virtual environment activated:

```powershell
cd tests
$env:PYTHONPATH = ".."
python -m pytest -q
cd ..
```

The tests exercise the local file reader without making model API calls.

To smoke-test ADK after setting `.env`, run from the parent directory:

```powershell
adk run code-review-agent
```

Submit a small snippet and confirm the agent returns findings. This smoke test requires a working model configuration and may incur API usage.

---

## Known Limitations

- The model may miss defects, misunderstand surrounding code, or report false positives.
- The agent does not compile, execute, lint, or run tests on the code under review.
- File review is limited to supported source extensions and files no larger than 100,000 bytes.
- The file reader can only access files inside the process's current working directory.
- Repository-wide context, dependency resolution, and cross-file data flow are not automatically analyzed.
- Model access, rate limits, latency, and API costs depend on the provider and account.

---

## Security & Privacy Considerations

- **Secrets Handling:** Credentials are loaded from a local `.env` file; `.env` is ignored by Git. Never paste secrets into prompts or reviewed files.
- **Data Privacy:** Code sent to the model is transmitted to the configured model provider and subject to that provider's terms and data policies. Do not submit confidential or regulated code unless approved.
- **File Access:** The helper reads supported source files only, rejects absolute paths and paths outside the working directory, and enforces a size limit.
- **Execution Safety:** The agent does not execute reviewed code or shell commands and does not edit files.
- **Human Review:** Treat results as suggestions, not as a replacement for security review, automated tests, or engineering judgment.

---

## Future Improvements

- [ ] Add optional unified-diff review.
- [ ] Add structured JSON findings for CI integration.
- [ ] Add language-specific static-analysis integrations.
- [ ] Add a repository-aware mode with explicit file selection.

---

## License

This project is contributed under the repository's open-source license.
