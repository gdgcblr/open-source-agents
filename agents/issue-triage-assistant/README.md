# GitHub Issue Triage Assistant

> Help maintainers decide whether an issue is actionable, see what information is missing, and review evidence-backed triage suggestions using a local Ollama model.

## Overview

### Problem Statement & Intended Users
- **Problem**: Maintainers spend time reading incomplete reports and asking for details already defined by their issue templates.
- **Intended Users**: Open-source maintainers who want a private, human-reviewed first pass on pasted issue reports.

### Key Features
- Checks triage readiness and identifies missing information.
- Explains the request and recommended maintainer next step in plain language.
- Shows exact quotes from the issue that support its summary and classification; quotes are checked against the original text.
- Checks supplied Markdown template headings and restricts suggested labels to a maintainer-provided list.
- Fetches a public GitHub issue and its repository labels from a read-only URL in the UI.
- Uses Google ADK with a local Ollama model. It never applies labels or posts replies.
- Includes offline mock mode and tests that do not require ADK or Ollama.

## Technical Stack
- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: Google Agent Development Kit (ADK), LiteLLM Ollama connector
- **User Interface**: Streamlit local chat UI
- **Models**: Default `llama3.2:3b` (configurable)
- **External APIs / Tools**: Local Ollama HTTP service; read-only public GitHub REST API

## Architecture & Data Flow

```text
Pasted issue or public GitHub issue URL + optional Markdown template
                         |
                         v
 GitHub REST API fetches public issue + repository labels (URL mode)
                         |
                         v
       ADK agent -> LiteLLM ollama_chat -> local Ollama model
                         |
                         v
 Validate JSON, exact evidence quotes, template fields, and label allowlist
                         |
                         v
 Print readiness, missing details, suggestions, evidence, and draft reply
```

Issue and template content are treated as untrusted data. The tool only prints recommendations for maintainer review.

## Prerequisites
- Python 3.10 or newer
- [Ollama](https://ollama.com/) running locally for live model triage
- Internet access when fetching a public GitHub issue (mock mode needs neither)
- An Ollama model installed (default: `llama3.2:3b`)

## Installation & Setup

```bash
cd agents/issue-triage-assistant
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
ollama pull llama3.2:3b
```

Ollama's server must be running. The ADK Ollama connector uses `OLLAMA_API_BASE`; the CLI sets it from `--host` or `OLLAMA_HOST` for each run.

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `OLLAMA_HOST` | No | `http://localhost:11434` | Local Ollama server URL |
| `OLLAMA_MODEL` | No | `llama3.2:3b` | Installed Ollama model name |
| `TRIAGE_LABELS` | No | *(empty)* | Comma-separated labels that exist in the repository |

The CLI reads these values from the process environment. It does not automatically load `.env` files.

## How to Run

Start the local chat UI:

```bash
streamlit run app.py
```

Open the local URL Streamlit prints (usually `http://localhost:8501`). In the sidebar, choose **Paste issue** or **Public GitHub issue**. For a GitHub issue, enter its public URL and select **Fetch and triage issue**. The assistant fetches its title and body plus the repository's labels, then runs triage with Ollama. The UI also lets you select mock mode, model, Ollama URL, and an optional Markdown template.

GitHub fetching is read-only and works with public issues without a token. Private repositories are not supported in this version. Unauthenticated GitHub API requests are rate limited, so occasional fetches may need to wait if the limit is reached.

The CLI remains available if you prefer the terminal:

Paste an issue title and description. Finish with Ctrl-D on macOS/Linux or Ctrl-Z then Enter on Windows:

```bash
python3 triage.py --labels bug,enhancement,question,documentation,needs-reproduction
```

Check the report against a repository issue template (Markdown headings are checked):

```bash
python3 triage.py \
  --labels bug,enhancement,question,documentation,needs-reproduction \
  --template path/to/ISSUE_TEMPLATE/bug_report.md
```

Print JSON or select a different installed Ollama model:

```bash
python3 triage.py --json --model llama3.2:3b
```

Run deterministic output without ADK or Ollama:

```bash
python3 triage.py --mock
python3 triage.py --mock --json
```

## Example Input & Output

### Example Input
```text
Title: Export crashes when saving a report
Description: When I click Export as PDF, the app closes without saving. This happens every time on macOS Sonoma 14.5.
```

### Example Output
```text
Summary: Export crashes when saving a report.
Issue type: bug
Maintainer guidance: The report describes a repeatable export crash. Ask for the app version and logs before estimating or assigning the fix.
Triage readiness: needs_information
Missing information:
- App version
- Error message or logs
Suggested labels (review before applying):
- bug
Evidence (exact quotes from the issue):
- summary: "Export crashes when saving a report"
- issue_type: "crashes"
Draft reply (review before posting):
Thanks for reporting this. Could you share your app version and any error message or logs?
```

Model responses vary. Exact evidence quotes that do not occur in the original issue are discarded. Suggestions should be reviewed before use.

## How to Test

From this directory, run the offline standard-library test suite:

```bash
python3 -m unittest -v
```

Tests cover JSON validation, evidence quote checks, readiness, template checks, label filtering, rendering, and ADK prompt construction using a fake responder. They make no network calls and require no API credentials.

## Known Limitations
- GitHub URL mode reads public issues and labels only; it does not access private repositories or post comments/apply labels.
- Public GitHub fetches require internet access and are subject to GitHub's unauthenticated API rate limit.
- Template checking is based on Markdown level-two headings and the model's assessment of the issue text.
- Evidence quotes support a claim but do not prove the claim is correct; maintainers should review the result.
- Local model quality and speed depend on the selected model and available hardware.

## Security & Privacy Considerations
- No GitHub credentials or cloud model API keys are needed for public issue fetches and local triage.
- GitHub issue text and repository labels are fetched read-only from `api.github.com`; issue text and optional template content are then sent to the configured Ollama endpoint.
- Issue and template text are sent to the configured Ollama endpoint. With the default URL they stay on the local machine; a remote endpoint receives that content.
- Issue text is untrusted input. The agent has no tools that can access files, run commands, or change repository state.
- Suggested labels and replies are not applied or posted automatically.

## Future Improvements
- [ ] Add private repository access through an optional fine-grained read-only token.
- [ ] Add duplicate candidates from the repository's open issues.
- [ ] Improve template parsing for checkboxes, required fields, and issue forms.
- [ ] Add a small evaluation set of real, anonymized issue examples and quality scores.

## License

This project is contributed under the repository's open-source license.
