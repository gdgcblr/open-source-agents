# Implementation Plan — git-commit-assistant

A Python CLI AI agent that reads the staged git diff and produces a Conventional
Commits message. Default path is a fully offline, deterministic `mock` provider so
the project runs on a clean clone with zero API keys (Reproducibility criterion).

## Design decisions (made here, grounded in the repo)

- **Package layout.** A thin `main.py` entry point plus a `commit_assistant/`
  package (`diff_parser.py`, `providers.py`, `message_builder.py`, `cli.py`,
  `__init__.py`). Rationale: CONTRIBUTING requires all code self-contained in the
  project folder and importable; splitting parse/build/provider keeps each unit
  small and unit-testable without git or network. `cli.py` holds arg parsing and
  orchestration so `main.py` stays a 3-line shim and tests can call the CLI
  programmatically.
- **Provider auto-selection.** `auto` (default) picks `openai` only if
  `OPENAI_API_KEY` is set AND the `openai` package imports; otherwise `mock`.
  An explicit `--provider` always wins over auto. `PROVIDER` env var sets the
  default provider when `--provider` is omitted. Rationale: matches the required
  "key present -> use it, else mock" behavior while keeping the clean-clone run
  on mock.
- **No network / no git in the mock path.** Mock uses stdlib only. `openai` is
  imported lazily inside the openai provider so a missing package never breaks
  the default path. Rationale: directly serves the Reproducibility requirement
  and the "stdlib only for mock" instruction.
- **Diff source.** Shell out to `git diff --staged` via `subprocess` from CWD;
  `--diff-file` bypasses git entirely for deterministic demos/tests. Rationale:
  the task mandates both; `--diff-file` is also how tests stay git-free.
- **Gemini provider.** Omitted from code to keep the build minimal (task says it
  is optional and only if it does not complicate things). `.env.example` keeps a
  commented `GEMINI_API_KEY` line and README lists it under Future Improvements.
  Rationale: mock + openai is the required minimum; adding a third SDK path adds
  risk for no judging benefit.
- **Python version.** Target Python 3.10+ (f-strings, `argparse`, `dataclasses`,
  `typing` all fine). Local env is 3.12.10, so tests will run.

## Module responsibilities

- `commit_assistant/diff_parser.py` — pure functions. Parse unified diff text into
  a `DiffSummary` dataclass: list of `FileChange(path, change_type, added,
  removed, ext)` where `change_type` ∈ {added, deleted, modified, renamed}, plus
  aggregate totals. No I/O.
- `commit_assistant/message_builder.py` — the mock heuristic. Turns a
  `DiffSummary` into a `CommitMessage(type, scope, subject, body_bullets)` and
  renders it to text. No I/O.
- `commit_assistant/providers.py` — `get_provider(name)`, `MockProvider` (wraps
  diff_parser + message_builder), `OpenAIProvider` (lazy import), auto-selection
  logic, and a shared `Provider.generate(diff_text, model, no_body) -> str`
  contract.
- `commit_assistant/cli.py` — argparse setup, reading the diff (git or file),
  friendly error handling, exit codes, printing to stdout.
- `main.py` — `from commit_assistant.cli import main; raise SystemExit(main())`.

## Mock heuristic rules (deterministic, documented in message_builder)

Decide the **type** (first match wins):
1. All changed files under `tests/`, `test/`, or matching `test_*.py`/`*_test.py`
   -> `test`.
2. All changed files are docs (`.md`, `.rst`, `.txt`, or under `docs/`) -> `docs`.
3. Any dependency/build manifest changed (`requirements.txt`, `pyproject.toml`,
   `package.json`, `Dockerfile`, `.gitignore`, CI yml) and nothing else notable
   -> `chore`.
4. Only file deletions, or net-negative lines with no new files and no new
   behavior signal -> `refactor`.
5. One or more **new** source files added -> `feat`.
6. Existing source modified with additions -> `fix` if a filename/path contains
   `fix`/`bug`, else `feat` if net lines added are substantial (> 10), else
   `chore`. (Keep rule simple and documented; ties resolve to `chore`.)

Decide the **scope**: the common top-level directory of changed paths if there is
exactly one (e.g. `commit_assistant`), the single filename stem if one file
changed, else omitted.

**Subject**: `<type>(<scope>): <summary>` (omit `(scope)` when none). Summary is a
deterministic phrase built from counts, e.g. `add diff_parser module`,
`update 3 files`, `remove legacy helper`. Imperative mood, lowercase start, no
trailing period, soft-capped at 72 chars.

**Body bullets** (suppressed by `--no-body`): one bullet per changed file up to a
cap of 10, formatted `- <verb> <path> (+A/-R)` where verb matches change_type
(add/update/delete/rename). If > 10 files, add a final `- …and N more files`.

## Provider auto-selection logic (providers.py)

```
resolve_provider(cli_flag, env):
    chosen = cli_flag or env.PROVIDER or "auto"
    if chosen == "auto":
        if env.OPENAI_API_KEY and openai_importable(): return "openai"
        return "mock"
    return chosen            # explicit flag/env wins, even if key missing
```
`OpenAIProvider.generate` raises a `ProviderError` with a friendly message when
the key is missing or `openai` import fails; `cli.py` catches it and exits 2.

## CLI flags (argparse in cli.py)

- `--provider {auto,mock,openai}` default `auto`.
- `--diff-file PATH` read diff text from a file instead of git.
- `--model NAME` optional model override (openai only; ignored by mock with a
  stderr note).
- `--no-body` subject line only.
- `--help` default argparse help, with a usage epilog showing a mock example.

Exit codes: `0` success; `1` no staged changes / empty diff (friendly message to
stderr); `2` git not found, provider/config error, or unreadable `--diff-file`.

---

## Steps

- [ ] 1. Create the package skeleton and `DiffSummary`/`FileChange` dataclasses with the unified-diff parser.
      Implement `parse_diff(text) -> DiffSummary` handling `diff --git`, `new file mode`, `deleted file mode`, `rename from/to`, and `@@`/`+`/`-` line counting; ignore `+++`/`---` header lines in counts. Pure stdlib, no I/O.
      Files: `commit_assistant/__init__.py`, `commit_assistant/diff_parser.py`
      Verify: `py -m pytest tests/test_diff_parser.py` (added in step 5) passes; until then `py -c "from commit_assistant.diff_parser import parse_diff; print(parse_diff('')):"` runs without import error from the project folder.

- [ ] 2. Implement the mock heuristic in `message_builder.py`.
      Add `CommitMessage` dataclass, `build_message(summary, no_body=False) -> CommitMessage`, and `render(msg) -> str` applying the type/scope/subject/body rules in this plan. Pure stdlib, deterministic.
      Files: `commit_assistant/message_builder.py`
      Verify: `py -m pytest tests/test_message_builder.py` (step 5) passes.

- [ ] 3. Implement `providers.py`: `Provider` base, `MockProvider`, `OpenAIProvider` (lazy `import openai`), `ProviderError`, `resolve_provider`, and `get_provider`.
      MockProvider composes `parse_diff` + `build_message` + `render`. OpenAIProvider builds a Conventional-Commits prompt from the diff, calls chat completions, returns the text; raises `ProviderError` with a clear message if key/package missing.
      Files: `commit_assistant/providers.py`
      Verify: `py -m pytest tests/test_providers.py` (step 5) passes — covers resolve_provider matrix and MockProvider end-to-end; OpenAIProvider missing-key path raises ProviderError (no network).

- [ ] 4. Implement `cli.py` and `main.py`: argparse, diff acquisition (git subprocess or `--diff-file`), orchestration, friendly errors, exit codes; print message to stdout.
      `read_staged_diff()` runs `git diff --staged` via subprocess, catches `FileNotFoundError` (git missing) and empty output; `--diff-file` reads the file with a clear error if absent. `main.py` is the shim calling `cli.main()`.
      Files: `commit_assistant/cli.py`, `main.py`
      Verify: from the project folder, `py main.py --diff-file tests/fixtures/add_module.diff --provider mock` prints a `feat(...)` message and exits 0; `py main.py --diff-file tests/fixtures/does_not_exist.diff` prints a friendly error and exits 2.

- [ ] 5. Add pytest suite and sample `.diff` fixtures (no network, no real git).
      Create fixtures: `add_module.diff` (new .py file), `fix_bug.diff` (modified source with 'fix' in path/body), `docs_only.diff` (README change), `delete_file.diff` (deleted file). Tests: `test_diff_parser.py` (counts, change types, rename), `test_message_builder.py` (type/scope/subject selection, `--no-body`, >10-file bullet cap), `test_providers.py` (resolve_provider matrix across flag/env/key presence, MockProvider output, OpenAIProvider ProviderError without key), `test_cli.py` (invoke `cli.main` with `--diff-file` for each fixture, assert exit codes and stdout). Use monkeypatch for env vars; never call real git/network.
      Files: `tests/__init__.py`, `tests/conftest.py`, `tests/fixtures/add_module.diff`, `tests/fixtures/fix_bug.diff`, `tests/fixtures/docs_only.diff`, `tests/fixtures/delete_file.diff`, `tests/test_diff_parser.py`, `tests/test_message_builder.py`, `tests/test_providers.py`, `tests/test_cli.py`
      Verify: from the project folder, `py -m pytest -q` — all tests pass with no network access.

- [ ] 6. Write `requirements.txt` (and note the optional openai install).
      Runtime deps: none beyond stdlib for the mock path — add a comment that `openai` is optional (`pip install openai==1.51.0`). Dev deps pinned: `pytest==8.3.3`. Keep it minimal and pinned per CONTRIBUTING.
      Files: `requirements.txt`
      Verify: from the project folder, `py -m pip install -r requirements.txt` succeeds on a clean venv; `py -m pytest -q` then passes.

- [ ] 7. Customize `.env.example` to only this project's vars.
      Replace template with: commented `OPENAI_API_KEY` (optional), commented `GEMINI_API_KEY` (optional/future), `PROVIDER=auto` with allowed values comment, commented `MODEL_NAME` with an openai default example. Remove PORT/HOST/LOG_LEVEL/SEARCH_API_KEY/DATABASE_URL/ANTHROPIC/TEMPERATURE lines.
      Files: `.env.example`
      Verify: read back the file — only OPENAI_API_KEY, GEMINI_API_KEY, PROVIDER, MODEL_NAME remain, each with placeholder + comment.

- [ ] 8. Extend `.gitignore` for Python/secrets (current template already covers most).
      Confirm it ignores `__pycache__/`, `*.pyc` (`*.py[cod]` present), `.venv/`, `.env`, `.pytest_cache/`; add `tests/fixtures/` exception note only if needed (fixtures ARE tracked, so do NOT ignore them). No change required beyond verifying; add `*.egg-info/` and `.coverage` if a gap exists.
      Files: `.gitignore`
      Verify: read back — Python patterns present; fixtures under `tests/fixtures/` are NOT ignored (confirm with `git -C <project> check-ignore tests/fixtures/add_module.diff` returns nothing).

- [ ] 9. Rewrite `README.md` from the template, filling every section with real content.
      Sections: Overview (problem = writing consistent Conventional Commits is tedious; users = developers), Key Features, Technical Stack (Python 3.10+, stdlib + optional openai), Architecture/Data Flow (diff -> parser -> heuristic/LLM -> message), Prerequisites, Installation & Setup with BOTH Windows PowerShell and Linux/macOS commands, Configuration table (OPENAI_API_KEY optional / GEMINI_API_KEY optional / PROVIDER / MODEL_NAME), How to Run with real examples, Example Input & Output copied from a REAL mock run (step 10), How to Test, Known Limitations (honest: mock is heuristic not semantic, Windows/Linux tested, openai untested without key), Security & Privacy (mock sends nothing off-machine; openai transmits diff to OpenAI), Future Improvements (gemini, local models), License.
      Files: `README.md`
      Verify: read back — no `[Project Name]` / bracketed placeholders remain; every heading has project-specific content.

- [ ] 10. Capture a REAL mock-mode run and paste its exact output into the README Example section.
      Run the tool against a committed fixture so the example is reproducible.
      Files: `README.md` (Example Input & Output section only)
      Verify: from the project folder, `py main.py --diff-file tests/fixtures/add_module.diff --provider mock` output matches, verbatim, the block pasted in README.

- [ ] 11. Add the Directory Index row in `agents/README.md` (the ONE allowed outside-folder edit).
      Replace exactly the single `*(None yet)*` placeholder row with: `git-commit-assistant` | short description | `Python 3.10+ / stdlib + optional OpenAI` | `shraddhagavade`.
      Files: `../README.md` (i.e. `c:\Users\A555902\Downloads\open-source-agents\agents\README.md`)
      Verify: read back — the `(None yet)` row is gone and replaced by the git-commit-assistant row; no other rows/files changed.

- [ ] 12. Final green check from the project folder.
      Files: none (verification only)
      Verify: `py -m pytest -q` passes; `py main.py --diff-file tests/fixtures/docs_only.diff --provider mock` prints a `docs:` message and exits 0; `py main.py --diff-file tests/fixtures/add_module.diff` (no flag, no key) auto-selects mock and prints a `feat` message.

## Notes / assumptions

- `py` launcher is used in verify commands (confirmed present as Python 3.12.10);
  `python` also works in this environment. The implementer should use whichever
  the environment exposes.
- Do NOT commit, push, or create a worktree (per task). Branch
  `feat/git-commit-assistant` is already checked out.
- The only file touched outside the project folder is the single index row in
  `agents/README.md`, which CONTRIBUTING explicitly permits.
