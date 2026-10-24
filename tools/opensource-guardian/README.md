# OpenSource Guardian

> A Streamlit-based tool that checks a project ZIP file for common open-source contribution readiness issues and produces an actionable report.

## Overview

### Problem Statement & Intended Users

**Problem:** New contributors may struggle to identify missing documentation, configuration problems, repository hygiene issues, and potential secrets before submitting a contribution.

**Intended users:** Open-source contributors, students, maintainers, and developers who want an initial checklist before opening a pull request.

OpenSource Guardian provides a preliminary readiness assessment. It is not a substitute for code review, security auditing, or project-specific contribution guidelines.

### Key Features

- Upload a project as a ZIP file for analysis.
- Check repository structure, documentation, configuration, and common project hygiene indicators.
- Identify potential issues and present actionable findings.
- Display a readiness score and a summary of checks.
- Optionally request an AI-generated explanation of findings using Google Gemini.
- Run the core checks locally without requiring an AI API key.

## Technical Stack

- **Language:** Python
- **User interface:** Streamlit
- **Core analysis:** Python
- **Optional AI explanation:** Google Gemini through the configured Python client
- **Input:** ZIP archive containing project files

## Architecture & Data Flow

1. `app.py` provides the Streamlit interface and handles the uploaded ZIP file.
2. `guardian.py` performs the readiness checks and prepares the findings.
3. `ai_explainer.py` optionally uses Google Gemini to explain the findings.
4. The interface displays the readiness score, check results, and explanations.

The core analysis does not require Gemini. The AI explanation feature requires a valid API key and an available model.

## Prerequisites

- Python compatible with the installed dependencies.
- pip.
- A web browser.
- A Google Gemini API key only if you want to use the optional AI explanation feature.

## Installation & Setup

Run these commands from the repository root:

```bash
cd tools/opensource-guardian

python -m venv .venv
```

Activate the virtual environment.

**Windows CMD:**

```cmd
.venv\Scripts\activate
```

**Linux/macOS:**

```bash
source .venv/bin/activate
```

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

## Configuration & Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | No | Google Gemini API key for the optional AI explanation feature. |

The core readiness checks can be used without this variable.

Set the key temporarily in Windows CMD:

```cmd
set GEMINI_API_KEY=your_api_key_here
```

On Linux/macOS:

```bash
export GEMINI_API_KEY="your_api_key_here"
```

Replace the placeholder with your own key locally. Never commit a real API key, `.env` file, or credentials to Git.

## How to Run

From `tools/opensource-guardian`, with the virtual environment activated:

```bash
streamlit run app.py
```

Streamlit will display a local URL in the terminal. Open that URL in your browser, upload a ZIP archive, and review the readiness report.

## Example Input & Output

**Input:** A ZIP archive containing a Python project.

**Expected output:** A readiness score, a summary of checks that passed or need attention, and findings intended to help the contributor improve the project before submitting it.

Exact results depend on the uploaded project's contents and the checks implemented by the tool.

## How to Test

1. Install dependencies using the instructions above.
2. Start the application with `streamlit run app.py`.
3. Upload a ZIP archive containing a small test project.
4. Verify that the application produces a readiness report.
5. If a Gemini API key is configured, test the optional AI explanation separately.

Automated tests should be added as the project evolves. Do not treat a successful application launch as proof that every check is correct.

## Known Limitations

- Readiness checks are heuristic and may produce false positives or miss issues.
- A readiness score does not guarantee that a project is secure, correct, or ready to merge.
- AI explanations depend on external API availability, model access, and API limits.
- ZIP archive validation and handling should be reviewed carefully for security and edge cases.
- Results depend on the files and project structure included in the uploaded archive.

## Security & Privacy Considerations

- The core readiness analysis is designed to run locally.
- Project findings may be sent to Google Gemini when the optional AI explanation feature is requested.
- Do not upload confidential source code, credentials, or sensitive data unless you are authorized to do so.
- The tool should inspect project files as data, not execute uploaded project code.
- Potential secret detection is not guaranteed to find every credential.
- Keep API keys in local environment variables and out of source control.

## Future Improvements

- Add automated unit tests and representative ZIP fixtures.
- Improve ZIP validation and edge-case handling.
- Expand readiness checks and document their criteria.
- Add clearer explanations and remediation guidance for individual findings.

## License

This tool is contributed under the open-source license of the parent repository. Refer to the repository's `LICENSE` file for the applicable terms.
