# FirstRun Doctor: scope and release plan

## Goal

Verify that a declared Python example creates its promised output. Keep observed
checks separate from suggested causes.

## Delivered scope

- Explicit command and JSON output contract.
- Preview by default; execution requires an explicit flag.
- Fresh working copies exclude old outputs and known credential files.
- Process status, fresh JSON, required types/values, and nonempty checks.
- Bounded logs, timeouts, redaction, and POSIX process cleanup.
- Terminal, JSON, Markdown, and before/after reports.
- Offline demo and optional Jev diagnosis.

The implementation is under `src/first_run_doctor/`. See [README](README.md) for
commands and [validation](docs/validation.md) for actual results.

## Release gates

1. Install the package in a fresh environment.
2. Run behavioral tests, lint, and formatting checks.
3. Run the installed wheel's offline demo outside the checkout.
4. Review source paths, process cleanup, secrets, and optional dependencies.
5. Save genuine sanitized examples and complete the upstream PR checklist.
6. Keep the contribution inside `tools/first-run-doctor/`.

## Deferred

Automatic fixes, dependency installation, arbitrary README execution, containers,
web UI, Windows execution, and framework adapters.

## Demo

Show a program that prints success but creates no report. Show Doctor's failed
file check. Run the corrected version, inspect its fresh output, and compare the
reports. See [demo steps](docs/demo.md).

The tool runs trusted local code as the current user. It is not an OS sandbox.
Passing confirms declared checks only, not general correctness.
