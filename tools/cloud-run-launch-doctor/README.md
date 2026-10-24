# Cloud Run Launch Doctor

> Turn Cloud Run build and startup logs into evidence-linked diagnoses and safe next steps, with optional Gemini explanations.

---

## Overview

### What Are We Building?

We are building a debugging assistant for developers using Google Cloud Run. When a deploy fails, developers often have a long build or revision log but no clear path from its error message to an actionable next step. The developer gives the tool a saved log file. A deterministic local diagnosis engine recognizes supported failure signatures, cites the exact matching line, and reports a likely cause, confidence level, and a safe next step. With an optional flag, Google ADK and Gemini explain that evidence in plain language.

The goal is to shorten the path from a failed deployment to a useful investigation. The existing project-directory scan remains available as a preflight check. This is not a deployment product or a complete Cloud Run validator.

### Problem Statement & Intended Users
- **Problem**: Cloud Run deploy failures can come from small configuration mistakes that are easy to spot in service files but confusing to diagnose.
- **Intended Users**: Developers preparing Python or Node.js services for Google Cloud Run, especially people learning the platform.

### Key Features
- Checks for common runtime manifests and basic Dockerfile startup configuration.
- Flags likely Python bind-address/port and Node.js `process.env.PORT` issues.
- Diagnoses common port, dependency, startup-command, memory, startup-probe, and scaling log failures with exact line evidence.
- Optionally cross-references a log diagnosis with related checks from the local service directory.
- Labels unknown logs as unclassified instead of inventing a cause.
- Redacts common credential formats from matched log evidence.
- Bounds Gemini calls with a configurable timeout so a slow request does not wait indefinitely.
- Includes an offline evaluator for synthetic fixtures and a private, local labeled-log dataset.
- Prints readable findings or JSON for scripts and CI workflows.
- Optionally uses a Gemini agent built with Google ADK to explain scanner findings or log diagnoses.

Deterministic rules are the source of truth for diagnosis and evidence. Gemini only explains their results; model output does not classify the log, alter confidence, or edit or deploy anything.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+ for the full project; deterministic scan code uses the standard library
- **Agent Framework / Core Library**: Google Agent Development Kit (`google-adk`)
- **Models**: Gemini via Google ADK, optional; default `gemini-flash-latest`
- **External APIs / Tools**: Gemini API only when `--explain` is enabled

---

## Architecture & Data Flow

The CLI has two local workflows. Directory scanning checks selected project files. Log diagnosis matches known signatures in a saved log and preserves line numbers. The optional `--project` argument cross-references related static findings, such as a port failure with a Python server that does not visibly use `PORT`. Both workflows work without a network request. With `--explain`, the CLI sends only structured findings or diagnoses to a Gemini agent; it does not send the full project or raw log file.

```text
[Project directory] --> [Static preflight] --+
                                             +--> [Evidence-backed report]
[Saved Cloud Run log] --> [Signature matcher] +
                              |                |
[Optional project dir] --> [Related checks] ---+
                                                   |
                                  optional --explain
                                                   v
                                         [ADK + Gemini]
                                                   v
                                            [Explanation]
```

---

## Prerequisites

- Python 3.10 or later for the full project and Google ADK
- For local checks only: no API keys or Google Cloud credentials
- For `--explain`: a Gemini API key from Google AI Studio

---

## Installation & Setup

1. Navigate to the project directory:
   ```powershell
   cd tools/cloud-run-launch-doctor
   ```
2. Create and activate a virtual environment. Core scanning and evaluation use only the standard library:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. To enable Gemini explanations, install the optional pinned dependency and set `GOOGLE_API_KEY` in your shell:
   ```powershell
   pip install -r requirements-adk.txt
   $env:GOOGLE_API_KEY="your-key"
   ```
   The CLI does not automatically load `.env` files.

---

## Configuration & Environment Variables

No environment variables are needed for the local scan. Gemini explanations require `GOOGLE_API_KEY`.

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | Only for `--explain` | None | Gemini API key used by Google ADK to explain findings. |

---

## How to Run

Run from this directory and provide the service directory to inspect:

```powershell
python main.py path\to\your\service
```

Use JSON output in automation, or strict mode to fail on warnings as well as errors:

```powershell
python main.py path\to\your\service --format json
python main.py path\to\your\service --strict
python main.py path\to\your\service --explain
```

Diagnose a saved Cloud Run log:

```powershell
python main.py --diagnose-log path\to\cloud-run.log
python main.py --diagnose-log path\to\cloud-run.log --format json
python main.py --diagnose-log path\to\cloud-run.log --explain
python main.py --diagnose-log path\to\cloud-run.log --project path\to\service --explain
python main.py --diagnose-log path\to\cloud-run.log --explain --explain-timeout 90
```

The log diagnosis workflow recognizes known signatures for port binding, missing runtime dependencies, dependency build failures, startup commands, memory limits, startup probes, and unavailable instances. Use `--project` to compare the log diagnosis with related local static checks. Run `python evaluate_fixtures.py` to print the offline benchmark as JSON. `--explain` requires Google ADK and `GOOGLE_API_KEY`; the default wait limit is 45 seconds and can be changed with `--explain-timeout`. Choose a different Gemini model with `--model model-name`.

Exit codes: `0` means no errors (and, in strict mode, no warnings); `1` means findings include errors or strict-mode warnings; `2` means the supplied path is not a directory.

---

## Example Input & Output

### Example Input

```powershell
python main.py --diagnose-log tests\fixtures\port_failure.log --project tests\fixtures\broken-port-service
```

### Example Output

```text
Cloud Run log diagnosis: tests\fixtures\port_failure.log
[WARNING] PORT_BIND_FAILURE (confidence: high)
  Likely cause: The container did not become ready on the port Cloud Run provided.
  Evidence, line 2: ERROR: The user container failed to start and listen on the port defined by PORT=8080.
  Next step: Check the service startup command and confirm the web server listens on 0.0.0.0 using the PORT environment variable.
  Project evidence [WARNING] PYTHON_BIND_ADDRESS: app.py starts a server without an obvious 0.0.0.0 bind address.
  Project evidence [WARNING] PYTHON_PORT: app.py starts a server without an obvious PORT environment setting.
```

---

## How to Test

From this directory, run:

```powershell
python -m unittest discover -s tests -v
```

The tests use temporary directories and checked-in log examples. They do not require network access, ADK, or cloud credentials. Run `python evaluate_fixtures.py` for accuracy, macro F1, per-category precision/recall/F1, and a confusion matrix. The fixture set includes synthetic cases and short error examples from Google's public [Cloud Run troubleshooting guide](https://docs.cloud.google.com/run/docs/troubleshooting). These examples check compatibility with documented wording; they are not customer logs or a representative production benchmark, and their score is not evidence of real-world accuracy.

To evaluate real examples locally, create a private dataset directory with `labels.json` and one log file per case. Keep the directory outside version control and remove or redact personal data, tokens, project IDs, and customer identifiers before evaluation. Example manifest:

```json
[
   {"id": "case-001", "file": "logs/case-001.log", "expected": "PORT_BIND_FAILURE"},
   {"id": "case-002", "file": "logs/case-002.log", "expected": "UNCLASSIFIED_LOG"}
]
```

Supported expected labels are `PORT_BIND_FAILURE`, `MISSING_DEPENDENCY`, `BUILD_DEPENDENCY_FAILURE`, `STARTUP_COMMAND_FAILURE`, `MEMORY_LIMIT`, `STARTUP_PROBE_FAILURE`, and `UNCLASSIFIED_LOG`. Run `python evaluate_fixtures.py --dataset C:\\private\\cloud-run-labels.json`. Evaluation is local; report output contains case IDs and labels, not raw log text. Use examples that were collected with permission and have been independently labeled; keep examples from the same deployment together in one split if you later create training/test partitions.

---

## Known Limitations

- Static checks are heuristic: framework-specific or indirect server startup patterns can be missed or flagged incorrectly.
- The log matcher recognizes a small set of textual signatures; wording varies across Cloud Run, Cloud Build, and application logs, so supported errors may be missed.
- A matched signature is a likely cause, not proof. Confirm with surrounding logs and service configuration.
- The 19-case benchmark is synthetic and hand-labeled; perfect fixture performance may reflect its narrow coverage and should not be presented as production accuracy.
- Local benchmark labels are only as reliable as the human annotations; ambiguous cases should be reviewed by a second person or marked unclassified.
- Credential redaction covers common token and key formats but cannot guarantee detection of every secret; review logs before sharing them with any service.
- Static project checks cover common Python and Node.js port patterns and basic Dockerfile startup commands; they are not a complete Cloud Run validator.
- It does not inspect Google Cloud project settings, IAM, billing, build logs, or deployment status.
- Gemini explanations are optional, require an API key, and may be inaccurate; always use the deterministic finding as the evidence and verify advice before acting.
- It does not automatically fix files or deploy services.

---

## Security & Privacy Considerations

- **Secrets Handling**: `GOOGLE_API_KEY` is read from the process environment only when `--explain` is used. Never commit a real key.
- **Data Privacy**: Scanning, log diagnosis, and benchmark evaluation are local. `--explain` sends structured findings or diagnoses (including matched, commonly redacted evidence text and file paths from optional project checks) to Gemini; source file contents and the full raw log are not sent by the tool. Never evaluate private logs until they have been reviewed for sensitive information.
- **Safety**: The checker does not execute inspected project code, run shell commands, modify files, or deploy resources.

---

## Future Improvements

- [ ] Support additional runtimes and framework-specific checks.
- [ ] Add opt-in, user-confirmed fix suggestions without automatic deployment.
- [x] Add synthetic log fixtures to regression-test supported diagnosis patterns.
- [ ] Expand the labeled benchmark with anonymized, consented real-world failures and measured precision/recall.

---

## License

This project is contributed under the repository's open-source license.