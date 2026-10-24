# FirstRun Doctor

> Check whether a local Python example creates the output it promises, and share the evidence.

## Overview

### Problem Statement & Intended Users

An AI agent can print "Success" and exit normally while never saving its promised
report. A leftover report can hide the same bug on the next run. FirstRun Doctor
checks a **fresh result**, including its declared content, and records the evidence.

It helps developers trying a local project, contributors preparing an example,
and maintainers reviewing a submission. Read the [simple overview](PROJECT_OVERVIEW.md)
for six everyday examples.

### Key Features

- Preview an explicit Python command and its prerequisites before allowing execution.
- Run it in a fresh working copy that excludes old declared outputs.
- Check JSON files, required fields, field types, expected values, and nonempty results.
- Capture bounded redacted logs; stop timed-out POSIX process groups.
- Produce terminal, JSON, and Markdown reports and compare equivalent reruns.
- Work offline. Optional Jev diagnosis suggests a cause without changing verification.

## Technical Stack

- Python 3.11+, standard-library core, `argparse` CLI, `unittest` tests.
- No agent framework, database, browser, or cloud deployment required.
- Optional `jev-latest` typed classification via Experiential Cloud; its extra uses
  `requests` and `python-dotenv`.
- MIT license, consistent with the parent repository.

## Architecture & Data Flow

```text
Local project + doctor.json -> preflight and preview
                  --execute -> fresh working copy -> selected Python command
                            -> process + output assertions -> evidence report
                            -> optional redacted Jev suggestion
Developer fixes source -> new run -> compare reports
```

Observed checks determine `verified`, `failed`, or `unknown`. Suggested causes are
separate. A model's confidence never changes a verification result.

## Prerequisites

- Python 3.11+ and pip.
- macOS or Linux for execution and process-group cleanup. Windows execution is
  unsupported in v0.1. Linux is intended to work but see the actual tested platforms
  in [validation notes](docs/validation.md).
- Trusted local Python source and a `doctor.json` contract. Doctor is **not an OS
  sandbox**; selected code runs as your current user.

## Installation & Setup

From a clone of the parent repository:

```bash
cd tools/first-run-doctor
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
first-run-doctor --version
first-run-doctor demo
```

The four bundled examples run without keys or network requests. Their actual
reports are written under a new `.doctor-reports/demo-*` directory. Dependencies
may be downloaded by pip during installation; the installed core has no runtime
dependencies. There is no requirement to install other monorepo projects.

For optional Jev diagnosis:

```bash
python -m pip install '.[jev]'
cp .env.example .env
# Edit the local .env to configure EXPERIENTIAL_API_KEY.
```

## Configuration & Environment Variables

| Setting | Required | Purpose |
| --- | --- | --- |
| `doctor.json` in target project | Yes | Command, inputs, timeout, required variable names, output assertions. |
| Variables in `required_env` | Only for that target | Read from the invoking environment and explicitly passed to the target. Values are not included in preflight metadata. |
| `EXPERIENTIAL_API_KEY` | Only for `--diagnose jev` | Read from the explicit local `--jev-env-file`; never passed to the target. |

Do not place credentials in command arguments or contracts. Jev's key must be in
the selected local `.env`; the adapter does not search parent folders or load a
different project environment automatically.

### Minimal contract

Put this `doctor.json` next to the target's `main.py`. Adjust it to the example's
actual promise. The command receives an argument list; shell operators and README
instructions are not interpreted.

```json
{
  "schema_version": 1,
  "command": ["{python}", "main.py"],
  "inputs": ["main.py"],
  "timeout_seconds": 10,
  "required_env": [],
  "artifacts": [
    {
      "path": "report.json",
      "format": "json",
      "checks": [
        {"field": "status", "equals": "complete"},
        {"field": "items", "type": "list", "nonempty": true}
      ]
    }
  ]
}
```

v0.1 supports local `.py` entrypoints and JSON objects with top-level field checks.
Types are `string`, `list`, `object`, `integer`, `number`, `boolean`, and `null`.
Boolean values do not count as integers. `equals` compares JSON types as well as
values. `nonempty` applies to strings, lists, and objects. Each artifact must have
at least one field assertion. Paths must be relative, non-overlapping, and cannot
overwrite the entrypoint, contract, manifest, or declared inputs. Use `inputs` to
protect additional required files from accidental output exclusion.

## How to Run

```bash
# Inspect a trusted project's contract and settings; does not execute it.
first-run-doctor inspect /path/to/project

# Preview is also the default for check.
first-run-doctor check /path/to/project

# Explicitly execute and write new reports outside the target project.
first-run-doctor check /path/to/project --execute --output-dir .doctor-reports/run-1

# Choose an installed target interpreter without provisioning dependencies.
first-run-doctor check /path/to/project --execute --python /absolute/path/to/python

# Return machine-readable observations on stdout.
first-run-doctor check /path/to/project --execute --format json

# Explicitly send bounded redacted evidence to Jev; may incur provider charges.
first-run-doctor check /path/to/project --execute --diagnose jev --jev-env-file .env

# Compare saved evidence; source changes are permitted, expectation changes disclosed.
first-run-doctor compare before/report.json after/report.json
```

Choose a new `--output-dir` for each run. Existing report directories are never
overwritten. A comparison checks the contract fingerprint, command, and interpreter;
it does not guarantee that the user's external environment stayed identical.

### Results and exit codes

| Exit | Meaning |
| --- | --- |
| `0` | Executed example verified; or inspection/preview completed successfully. Preview runtime verification is still `unknown`. |
| `1` | Observed failure: nonzero exit, missing output, invalid JSON, or failed assertion. |
| `2` | Invalid configuration, unsupported operation, or Doctor error. |
| `3` | Requested execution incomplete: missing required configuration/input, timeout, or unreadable/oversize evidence. Also used for a comparison with changed expectations or interruption. |

## Example Input & Output

The packaged `false-success` example prints "Report created successfully" but
does not create `report.json`:

```bash
first-run-doctor check src/first_run_doctor/fixtures/false-success --execute
```

Excerpt from a genuine run:

```text
FIRST RUN DOCTOR
Verification: FAILED
Execution: completed

PASS    ENTRY   Declared Python entrypoint: main.py
PASS    INPUT1  Declared input: main.py
INFO    MANIFEST Dependency manifest: None found; stdlib-only examples may not need one
PASS    EXEC    Command exit status: 0
FAIL    A1      Fresh report.json: Expected artifact missing
SKIPPED A1.1    status: Artifact missing
SKIPPED A1.2    items: Artifact missing

Next step: Check the code that creates the declared output and its required fields, then rerun.
```

The `working` example creates a fresh report with a complete status and a nonempty
list. The same assertions then pass. The one-command demo executes both and saves
the comparison. See [the demo walkthrough](docs/demo.md) and the curated actual
reports in [examples/results](examples/results/).

## How to Test

```bash
python -m unittest discover -s tests -v
first-run-doctor demo
```

The tests exercise real short-lived subprocesses, stale artifacts, symlink/path
rejection, invalid output, secret redaction, timeouts, and comparisons. Optional
Jev transport tests use mocks and are skipped when its extra is absent. No test
needs a live model key. [Validation notes](docs/validation.md) record actual checks;
[contributor instructions](CONTRIBUTING.md) explain where files belong and how to
prepare a clean PR.

## Known Limitations

- Checks declared examples, not overall correctness or answer truth.
- Uses an installed interpreter; does not install target dependencies or verify
  arbitrary README setup on a fresh machine.
- Supports local `.py` scripts and top-level JSON fields on POSIX. Windows execution
  is unsupported. See [tested platforms](docs/validation.md).
- Copy limits: 1,000 files, 2 MiB each, 20 MiB total. Artifact reads: 2 MiB.
  Log capture: 64 KiB per stream. Execution timeout: 0.1-120 seconds.
- Unsupported symlinks are rejected. Timed-out or incomplete runs stay unverified.

## Security & Privacy Considerations

- Run trusted local code only. A temporary copy is not a sandbox; target code can
  still access your files, network, and OS resources.
- Known credential files and `.env` are excluded. The child receives a minimal
  environment plus declared target variables, without Doctor's model key.
- Logs use best-effort redaction and terminal-control removal. Reports contain
  artifact hashes, not artifact contents. Review reports before sharing.
- Only explicit `--diagnose jev` sends evidence: at most 24 bounded check entries
  and 4,000 stderr characters. TLS is verified; redirects and automatic retries
  are disabled. Connect/read timeouts are 10/60 seconds. Provider charges may apply,
  including after a timeout. API failure leaves verification usable.

See [security notes](docs/security.md) for controls and remaining limits.

## Future Improvements

- Explicit opt-in dependency provisioning in a disposable environment.
- A Google ADK adapter using the same verification functions.
- More artifact types and nested schema checks.
- Windows process-tree cleanup, with platform tests before claiming support.

## License

This project is contributed under the repository's MIT license. See [LICENSE](LICENSE).
