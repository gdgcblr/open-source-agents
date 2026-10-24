# Contributing to FirstRun Doctor

This tool belongs at **`tools/first-run-doctor/`** in the parent monorepo. It is a
developer utility, not an entry under `agents/`.

## Where to add changes

- `src/first_run_doctor/`: implementation; core stays usable without optional APIs.
- `src/first_run_doctor/fixtures/`: tiny trusted examples shipped in the wheel.
- `tests/`: behavior and regression checks; mock network transport, not subprocess behavior.
- `docs/`: tested usage, demo steps, limitations, and security notes.
- `examples/results/`: only selected sanitized reports from actual example runs.
- `pyproject.toml`: local dependencies and packaging. No parent build-file changes.

Do not add downloaded skills, credentials, virtual environments, generated local
runs, or unrelated files. The optional parent `tools/README.md` index row is the
only change outside this folder allowed by the upstream contribution guide.

## Local check sequence

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
python -m unittest discover -s tests -v
first-run-doctor demo
```

For transport tests, install `python -m pip install '.[jev]'` and run the same
suite. Test logs use made-up values; never put a real key in a fixture.

If available, run `ruff check src tests` and `ruff format --check src tests`.
Verify a built wheel in a separate virtual environment and run its offline demo
from outside the checkout, so source files cannot hide missing package data.

## Before opening a PR

1. Read the parent `CONTRIBUTING.md` and PR template; use its fork/feature-branch workflow.
2. Keep verification facts separate from diagnosis. Exit zero alone is never a pass.
3. Add a regression for a meaningful behavior change; run the relevant existing tests.
4. Update the contract/CLI docs when behavior changes and regenerate affected
   curated reports from real runs. State when a fixture is synthetic.
5. Check `git diff --check`, review the exact staged paths, and scan for secrets.
6. Complete the upstream PR checklist with the actual commands and environments tested.

Maintainers decide whether to merge. Do not bypass review, add root workflows, or
claim that these examples establish production readiness or a general benchmark.
