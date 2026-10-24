# StackTrace Copilot

> A Python CLI debugging assistant that analyzes stack traces and error logs, identifies source locations, and recommends practical debugging steps.

---

## Overview

### Problem Statement & Intended Users

* **Problem**: Developers often spend significant time understanding error logs, locating failing code, and identifying the next debugging steps.
* **Intended Users**: Software developers, QA engineers, DevOps engineers, and contributors troubleshooting application failures or automated test results.

### Key Features

* **Exception Detection**: Identifies recognized exception types and extracts relevant error messages.
* **Stack Trace Parsing**: Extracts file paths, line numbers, and function names from common Python and JavaScript stack traces.
* **Diagnostic Suggestions**: Uses rule-based analysis to suggest possible causes and practical verification steps.
* **Structured Output**: Provides human-readable reports and machine-readable JSON output.
* **Local Execution**: Runs locally without requiring an LLM API key or external service.

---

## Technical Stack

* **Language & Runtime**: Python 3.11+
* **Agent Framework / Core Library**: Python standard library with deterministic, rule-based diagnostic logic.
* **Models**: None required in the initial version.
* **External APIs / Tools**: None.
* **Testing Framework**: pytest.

---

## Architecture & Data Flow

StackTrace Copilot reads a local error-log file, extracts the exception message and source locations, applies diagnostic rules, and produces debugging suggestions with verification steps.

```text
[Error Log File]
       |
       v
[Input Reader]
       |
       v
[Exception and Stack Frame Parser]
       |
       v
[Rule-Based Diagnostic Engine]
       |
       v
[Suggested Checks and Verification Steps]
       |
       v
[Human-Readable Report or JSON Output]
```

---

## Prerequisites

Before running this project, ensure you have:

* Python 3.11 or newer.
* pip package manager.
* A text file containing an error log or stack trace.
* No API keys or external service accounts are required.

---

## Installation & Setup

1. **Navigate to the project directory:**

   ```bash
   cd tools/stacktrace-copilot
   ```

2. **Set up the virtual environment and install dependencies:**

   ```bash
   python3 -m venv .venv
   ```

   Activate the environment on Linux/macOS:

   ```bash
   source .venv/bin/activate
   ```

   On Windows:

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

   Install the dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**

   No environment variables or API keys are required for the initial version. The `.env.example` file is included to follow the repository's tool directory conventions.

---

## Configuration & Environment Variables

The initial version does not require environment variables.

No `.env` file is needed to run the tool. If an LLM provider is added in a future version, its configuration will be documented here.

---

## How to Run

Analyze the included sample error log:

```bash
python main.py --file examples/sample.log
```

Generate a JSON report:

```bash
python main.py --file examples/sample.log --json
```

Analyze a custom error log:

```bash
python main.py --file /path/to/error.log --json
```

The tool reads the supplied text file and reports the detected error, extracted source locations, diagnostic suggestions, and verification steps.

---

## Example Input & Output

### Example Input

```text
Traceback (most recent call last):
  File "/app/service.py", line 42, in process_request
    return user.profile.name
AttributeError: 'NoneType' object has no attribute 'profile'
```

### Example Output

```text
Error: AttributeError: 'NoneType' object has no attribute 'profile'
Type: AttributeError
Diagnosis: An object does not expose the requested attribute.
Confidence: medium

Source locations:
  /app/service.py:42 (process_request)

Suggested checks:
  - Inspect the object's runtime type and available attributes.
  - Check for misspelled names or unexpected None values.
```

The exact output depends on the input log. Diagnostic suggestions are heuristics and do not guarantee identification of the actual root cause.

---

## How to Test

Run the automated test suite from the project directory:

```bash
python -m pytest -v
```

The tests cover:

* Exception extraction.
* Python stack-frame parsing.
* JavaScript stack-frame parsing.
* Handling of unrecognized errors.
* Diagnostic suggestions.
* JSON serialization.
* CLI execution and output.

---

## Known Limitations

* Diagnosis is rule-based and may not identify the actual root cause.
* Only selected exception types and common stack-frame formats are recognized.
* The initial version does not inspect source repositories or automatically generate code patches.
* LLM-powered reasoning and external debugging integrations are not included.
* Unusual or incomplete stack traces may not be parsed correctly.

---

## Security & Privacy Considerations

* **Secrets Handling**: The initial version does not require credentials or API keys.
* **Data Privacy**: Input logs are processed locally and are not transmitted to external services by this implementation.
* **Safety**: The tool does not execute arbitrary shell commands or modify source files.
* **Sensitive Data**: Error logs may contain tokens, credentials, or personal information. Review logs before sharing them.

---

## Future Improvements

* [ ] Support additional programming languages and stack-trace formats.
* [ ] Extract relevant source-code context when provided.
* [ ] Add optional LLM-powered debugging with explicit privacy controls.
* [ ] Improve confidence reporting and structured output validation.
* [ ] Integrate with CI pipelines and automated test reports.
* [ ] Add optional MCP server support for developer workflows.

---

## License

This project is contributed under the repository's open-source license.
