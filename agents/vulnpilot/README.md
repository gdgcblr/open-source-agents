# VulnPilot

> A safe CLI tool that scans projects with Semgrep and optionally provides Google Gemini-assisted security finding analysis.

## Overview

VulnPilot helps developers and security learners identify and review potential security issues in their projects. It runs Semgrep, displays findings in a readable format, and optionally uses Google Gemini to provide advisory recommendations.

### Key Features

- **Security scanning:** Scan a target project using the Semgrep CLI.
- **Readable results:** Display findings with severity, file location, rule ID, and message.
- **Markdown reports:** Save scan results to a Markdown report.
- **Optional AI analysis:** Use Google Gemini to help understand findings and suggest possible remediation steps.
- **Offline mock mode:** Demonstrate and test the workflow without running a real security scan or calling the Gemini API.
- **Safe operation:** Report findings and recommendations without automatically modifying source files or applying patches.

## Technical Stack

- **Language:** Python
- **Security scanner:** Semgrep CLI
- **AI integration:** Official Google GenAI Python SDK (`google-genai`)
- **Environment configuration:** `python-dotenv`
- **Testing:** `pytest`

## Architecture & Data Flow

1. The user provides the path to a project to scan.
2. VulnPilot validates the target directory.
3. Semgrep scans the project and returns results in JSON format.
4. VulnPilot parses the results and displays a readable summary.
5. The user can optionally save the findings to a Markdown report.
6. If AI analysis is explicitly enabled, finding metadata is sent to the Google Gemini API for advisory analysis.
7. The user reviews the findings and recommendations and decides what action to take.

VulnPilot does not automatically patch source code or apply suggested fixes.

## Prerequisites

- Python 3.10 or later.
- `pip` for installing Python dependencies.
- Semgrep CLI for real security scans.
- A Google Gemini API key only if AI analysis is required.
- Internet access for Gemini API requests.

## Installation & Setup

From the repository root, navigate to the VulnPilot directory:

```bash
cd agents/vulnpilot
```

Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows, activate the environment using:

```powershell
.venv\Scripts\activate
```

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

For real scans, ensure the Semgrep CLI is installed and available in your environment.

To configure optional Gemini integration, create a local environment file:

```bash
cp .env.example .env
```

Add your Gemini API key to `.env` only if you intend to use AI analysis. Never commit real API keys or other secrets.

## Configuration & Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | No | None | Required only when AI analysis is enabled |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Optional Gemini model override |

AI analysis is optional. VulnPilot can run its offline mock demonstration without a Gemini API key.

## How to Run

### 1. Run a Security Scan

Replace `/path/to/your/project` with the path to the directory you want to scan.

```bash
python main.py /path/to/your/project
```

### 2. Save a Markdown Report

```bash
python main.py /path/to/your/project --report report.md
```

### 3. Enable AI Analysis

```bash
python main.py /path/to/your/project --ai
```

Ensure `GEMINI_API_KEY` is configured before enabling AI analysis.

### 4. Run the Offline Mock Demonstration

The mock demonstration is useful for checking the CLI and report workflow without running a real security scan or calling the Gemini API.

```bash
python main.py . --mock --mock-ai --report mock-report.md
```

The generated report is saved to the specified path.

## Example Input & Output

**Example command:**

```bash
python main.py . --mock --mock-ai --report mock-report.md
```

**Example output:**

```text
VulnPilot: 1 finding(s)
[WARNING ] example.py:1:1  MOCK.demo-rule
           Mock finding for offline demonstration.

AI recommendations (advisory only):
Offline mock analysis: verify each finding, confirm exploitability, and review any proposed fix manually.

Markdown report saved to mock-report.md
```

*This is illustrative mock output, not the result of a real vulnerability scan.*

## How to Test

Run the test suite from the VulnPilot directory:

```bash
python -m pytest -v
```

The tests cover scanner finding parsing, malformed scanner output, invalid targets, offline mock scanning, AI behavior when an API key is unavailable, and CLI/report functionality.

The mock tests do not require a live Gemini API call.

## Known Limitations

- Real security scans require the Semgrep CLI to be installed and working.
- Gemini analysis requires a valid API key and network access.
- AI recommendations may be incomplete or inaccurate and must be reviewed manually.
- Mock mode verifies the workflow but does not measure real vulnerability detection quality.
- A scan reporting zero findings does not guarantee that a project is free from vulnerabilities.

## Security & Privacy Considerations

- **Secrets handling:** Credentials are loaded from environment variables or a local `.env` file. Never commit real API keys or credentials.
- **Data privacy:** Real scans run through Semgrep. When AI analysis is enabled, finding metadata is sent to Google's Gemini API. Do not enable AI analysis for sensitive findings unless sharing that information is authorized.
- **Safe operation:** VulnPilot reports findings and recommendations; it does not automatically modify scanned source files or apply patches.
- **Authorized scanning:** Only scan projects you own or have permission to assess.
- **Recommendation review:** Verify findings and assess suggested fixes before making changes to a project.

## Future Improvements

- Add SARIF report export.
- Support configurable Semgrep rulesets.
- Improve finding deduplication and prioritization.
- Enhance reporting and vulnerability summaries.

## License

This project is contributed under the repository's open-source license.
