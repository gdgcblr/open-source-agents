# SecurePR AI

> A security review agent that combines deterministic code checks, risk prioritization, and an optional AI-assisted review dashboard for pull requests.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Pull request reviews can miss common authentication, authorization, and secret-handling mistakes, while generic AI reviews may produce findings without clear evidence.
- **Intended Users**: Developers, application security teams, and maintainers who want a local security review workflow and actionable findings for code changes.

### Key Features
- Scans Python, JavaScript, TypeScript, JSON, environment, and YAML files for selected JWT, credential, API authorization, and CORS patterns.
- Prioritizes findings by severity and exposure context, correlates selected findings into STRIDE threat hypotheses, and produces Markdown or JSON reports.
- Includes a local web dashboard with sample reviews, file upload, GitHub pull request ingestion, fix verification, and optional Gemini explanations/chat.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+ for the CLI; Node.js 20+ for the dashboard
- **Agent Framework / Core Library**: Python CLI and deterministic rules; React, Vite, and Express for the dashboard
- **Models**: Gemini model access through Google GenAI when `GEMINI_API_KEY` is configured; deterministic/offline responses otherwise
- **External APIs / Tools**: GitHub REST API for pull request ingestion; Pydantic and PyYAML for the Python package

---

## Architecture & Data Flow

The CLI reads local source files or GitHub pull request patches, redacts recognized credentials in evidence, applies deterministic checks, prioritizes findings, and emits a report. The dashboard provides a React interface backed by an Express API; when configured, selected redacted finding context is sent to Gemini for explanations and chat responses.

```
[Local files / GitHub PR patches]
               |
               v
[Credential redaction + deterministic checks]
               |
               v
[Risk ranking + STRIDE hypotheses]
          /           \
         v             v
[CLI reports]    [Dashboard / optional Gemini]
```

---

## Prerequisites

- Python 3.10 or newer and pip
- Node.js 20 or newer and npm, only for the web dashboard
- Optional: a Gemini API key for generated explanations and conversational review
- Optional: a GitHub token for private pull requests or higher GitHub API rate limits

---

## Installation & Setup

### Python CLI

```bash
cd agents/securepr-ai
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
```

### Web Dashboard

From the same directory (the Python package install is not required for the dashboard):

```bash
npm install
Copy-Item .env.example .env  # Windows PowerShell
# Linux/macOS: cp .env.example .env
npm run dev
```

Open `http://localhost:3000`. The dashboard includes synthetic sample pull requests for local exploration; fetching a real pull request is optional.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | No | None | Enables Gemini explanations and chat. Without it, the dashboard and Python agent use deterministic/offline responses. |
| `GITHUB_TOKEN` | No | None | Used by the Python CLI for private PR access and by the dashboard as a fallback token. |
| `PORT` | No | `3000` | Port for the Express dashboard server. |
| `NODE_ENV` | No | `development` | Use `production` to serve the built dashboard instead of Vite middleware. |

The Python `scan-pr` command also accepts `--token`; the dashboard accepts a token in its pull request import dialog. Keep `.env` private and never commit real credentials.

---

## How to Run

Run the deterministic benchmark:

```bash
python -m securepr_agent.cli benchmark
```

Scan a local directory and write reports:

```bash
python -m securepr_agent.cli scan --path . --fail-on HIGH --exposure PUBLIC --md-out report.md --json-out report.json
```

Fetch and scan a GitHub pull request:

```bash
python -m securepr_agent.cli scan-pr --pr-url https://github.com/owner/repo/pull/42
```

Start the web dashboard with `npm run dev`; use `npm run build` to build its static frontend.

---

## Example Input & Output

Given a changed file containing `claims = jwt.decode(token, verify=False)`, the CLI reports a JWT signature-verification finding with a file and line location, a severity/risk score, remediation guidance, and a pass/fail gate result. Actual findings depend on the patterns and exposure policy configured in the scanner.

---

## How to Test

From this directory, run the Python tests and benchmark:

```bash
python -m pytest
python -m securepr_agent.cli benchmark
```

For the web dashboard, run `npm run lint` (TypeScript check) and `npm run build`.

The benchmark is a small, synthetic rule-regression suite; its reported metrics describe only those included cases and are not a guarantee of real-world detection accuracy.

---

## Known Limitations

- Detection uses narrow deterministic patterns and heuristics, not complete language parsing or whole-program data-flow analysis; results require human review.
- GitHub ingestion analyzes pull request patches and may lack surrounding file context. Large pull requests can also be limited by GitHub API pagination and response caps.
- Gemini explanations are optional and send the redacted finding context to Google's API when enabled.
- The dashboard server has no authentication and binds to all interfaces. Use it only on a trusted machine/network; do not expose it publicly as-is.
- The synthetic benchmark is small and must not be interpreted as a broad security efficacy claim.

---

## Security & Privacy Considerations

- Recognized secrets are redacted from finding evidence before reports or configured AI prompts are generated. Redaction is pattern-based and cannot guarantee removal of every secret format.
- Local scans process source files on the machine. GitHub PR ingestion contacts GitHub; Gemini requests are made only when `GEMINI_API_KEY` is set.
- The scanner analyzes text and does not execute reviewed source code.
- GitHub tokens and Gemini keys must be supplied locally through environment variables or the PR import dialog. Do not expose the unauthenticated dashboard to untrusted users.

---

## Future Improvements

- [ ] Add broader language-aware analysis and more comprehensive tests.
- [ ] Add SARIF report output for code-scanning integrations.
- [ ] Add authentication and deployment hardening for the web dashboard.

---

## License

This project is contributed under the repository's open-source license.
