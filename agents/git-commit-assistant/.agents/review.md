# git-commit-assistant: offline-first Conventional Commits generator

A Python CLI that turns a staged git diff into a Conventional Commits message. The default `mock` provider is a deterministic, stdlib-only heuristic that inspects file paths, extensions, and added/removed line counts — no API key, no network, so a reviewer can `pip install -r requirements.txt` and run it on a clean clone. An optional `openai` provider imports the SDK lazily and is selected only when `OPENAI_API_KEY` is set and the package is importable. The module split (`diff_parser` → `message_builder` → `providers` → `cli`, with a three-line `main.py` shim) keeps each unit pure and testable, and a 41-test pytest suite exercises the mock path against checked-in `.diff` fixtures with no git or network.

Watch for: nothing blocking. The implementation, verification evidence, and documentation all line up with the requirements; the one outside-folder edit is exactly the single permitted index row (confirmed). The mock heuristic is intentionally syntactic, not semantic, and the README states this limitation honestly (confirmed).

**Verdict**: APPROVED

## High-level view

The reproducibility requirement is the center of gravity and it holds. The default path resolves to `mock` whenever no key is present, the mock provider pulls in nothing beyond the standard library, and `requirements.txt` pins only `pytest` for development while leaving the runtime dependency-free. A clean-clone run needs zero configuration (confirmed from code and from the recorded verification run).

Provider selection matches the spec precisely: `resolve_provider` returns `openai` only when both `OPENAI_API_KEY` is set and the `openai` module is importable, otherwise `mock`; an explicit `--provider` flag or `PROVIDER` env var always overrides auto. The `openai` import lives inside the provider method, so a missing package never disturbs the default path, and the missing-key and missing-package cases raise a friendly `ProviderError` rather than a traceback (all confirmed, with the missing-key/package paths covered by tests).

The CLI surface is complete and the failure modes map to distinct exit codes: `0` success, `1` empty/no staged changes, `2` git-missing or unreadable diff file or provider error. `git diff --staged` runs with a fixed argument list through `subprocess` (no shell string), and `--diff-file` bypasses git entirely, which is also how the tests stay git-free (confirmed).

Documentation is filled end to end — both Windows PowerShell and Linux/macOS setup, a configuration table, a Security & Privacy section that correctly distinguishes the local-only mock path from the diff-transmitting openai path, and honest limitations. The README's Example Output is reproducible: tracing the heuristic by hand against the committed `add_module.diff` and `docs_only.diff` fixtures yields exactly the pasted blocks, and both match the recorded verification output (confirmed).

Scope is tight. Everything lives inside the project folder; the sole edit outside it is the one Directory Index row in `agents/README.md` for contributor `shraddhagavade`, which CONTRIBUTING permits. No secrets, no `.venv`, no `.env`, and no cache artifacts were left behind (confirmed by git status and a filesystem scan).

<details>
<summary>Issues (0)</summary>

No blocking or non-blocking action items. The review surfaced no concerns.

</details>

<details>
<summary>Details</summary>

### Reproducibility: the mock path is genuinely stdlib-only

`MockProvider.generate` calls `parse_diff` → `build_message` → `render`, and those three modules import only `os`, `dataclasses`, and `typing`. `providers.py` adds `importlib.util` — also stdlib — used by `_module_available` to probe for the `openai` package via `find_spec` without importing it. The actual `import openai` is inside `OpenAIProvider.generate`, unreachable on the default path. `requirements.txt` carries no runtime packages, offers `openai` as an optional unpinned install, and pins `pytest==8.3.3` for development only — so a clean clone installs the requirements and runs `python main.py` with no key.

The recorded verification shows this end to end: with no `OPENAI_API_KEY`, `python main.py --diff-file ...\add_module.diff` auto-selected mock and printed `feat(commit_assistant): add greet module` plus the bullet body at exit 0.

### Provider auto-selection and lazy openai import

`resolve_provider(cli_flag, env)` collapses flag → `PROVIDER` env → `"auto"`, lowercases, validates against `{auto, mock, openai}` (raising `ProviderError` on an unknown name), and for `auto` returns `openai` only when `env.get("OPENAI_API_KEY")` is truthy *and* `_module_available("openai")`. Any explicit choice short-circuits that logic, so `--provider` wins even when the key is absent — matching the spec's "explicit flag overrides" clause. The resolution matrix is covered by `test_providers.py` across flag-wins, env-used, auto-without-key, auto-with-key-no-package, auto-with-key-and-package, and unknown-name cases, using `monkeypatch` to stub `_module_available` so no real SDK is needed.

`OpenAIProvider.generate` checks the key first, then package availability, raising a friendly `ProviderError` for each before any import. Both error paths are tested; the actual network call is wrapped and marked `pragma: no cover`.

### CLI contract and failure modes

`build_parser` defines all required flags — `--provider {auto,mock,openai}` (default auto), `--diff-file PATH`, `--model NAME`, `--no-body` — and argparse supplies `--help` with a usage epilog of real examples. `--model` against the mock provider emits a non-fatal stderr note rather than failing (tested).

The exit codes are distinct: git-not-found and git-command-failure become a `ProviderError` → exit 2; a missing `--diff-file` → exit 2; an empty diff → a "No staged changes found" stderr message → exit 1; success → exit 0. `read_staged_diff` invokes `["git", "diff", "--staged"]` as an argument list with `capture_output`/`text`, so there is no shell interpolation of any user-controlled value. The CLI tests invoke `cli.main([...])` programmatically with `--diff-file` fixtures, so they never shell out to real git.

### Diff parser and the deterministic heuristic

`parse_diff` walks the unified diff line by line: `diff --git` opens a file block (defaulting to the `b/` path), `new file mode`/`deleted file mode`/`rename from|to` set the change type, `rename to` and a non-`/dev/null` `+++` line update the path, and `+`/`-` lines increment counts while `+++`/`---` headers are explicitly excluded from the counts. Unrecognized input is skipped rather than raising, so malformed diffs degrade to an empty summary. The `test_header_lines_not_counted` case pins the off-by-one guard (6 added, not 7), and `test_multiple_files` confirms multi-file aggregation and mixed change types.

The heuristic in `message_builder._decide_type` applies first-match-wins rules: all-tests → `test`, all-docs → `docs`, all-manifest → `chore`, all-deletions → `refactor`, any added source → `feat`, else a `fix`/`bug` path signal → `fix`, else size-based `feat`/`chore`. The ordering resolves the natural overlaps correctly — a manifest with a doc-like extension is excluded from the docs rule by `_is_manifest_path`, and `setup.py` is classified `chore` while still yielding a `setup` stem scope (tested). Scope is the common top-level directory, or a single root file's stem, or omitted; subjects are deterministic phrases soft-capped at 72 chars; the body emits one bullet per file up to ten, then an "…and N more file(s)" line (the 13-file case is tested to produce exactly 11 bullets).

Tracing the committed fixtures by hand reproduces the README's Example Output exactly. `add_module.diff` (one added `.py` under `commit_assistant/`) yields `feat(commit_assistant): add greet module` with `- add commit_assistant/greet.py (+6/-0)`. `docs_only.diff` (one modified root `README.md`) yields `docs(README): update README.md documentation` with `- update README.md (+2/-0)`. Both match the pasted blocks and the recorded verification output, so the documented example is genuinely reproducible rather than hand-written.

### Test coverage

The 41-test suite (recorded as `41 passed in 0.11s`) spreads across the parser (counts, change types, rename, header exclusion, multi-file), the heuristic (every type rule, scope selection, no-body suppression, bullet cap, subject cap), provider resolution (the full flag/env/key matrix plus error cases), and the CLI (each fixture's exit code and stdout, missing file, empty file, auto-without-key, model-ignored note). `conftest.py` puts the project root on `sys.path` and exposes fixture helpers; env is manipulated only through `monkeypatch`. Nothing calls real git or the network.

Not tested: the live OpenAI request path (expected — it needs a real key; its guard clauses are tested and the call is `pragma: no cover`) and `read_staged_diff`'s real-git branch (the git-missing path is reachable only with git absent from PATH). Both omissions are reasonable and the README's Known Limitations states the openai path is not exercised.

### Security, scope, and hygiene

`OPENAI_API_KEY` is read from the environment only and never logged or written; `.env` is git-ignored (`.env`, `.env.*` with a `!.env.example` negation). The `.gitignore` covers `__pycache__/`, `*.py[cod]`, `.venv/`, `.env`, `.pytest_cache/`, plus key/credential patterns. `.env.example` is trimmed to only the four variables the project actually uses — `OPENAI_API_KEY`, `GEMINI_API_KEY` (marked future), `PROVIDER`, `MODEL_NAME` — each commented, no leftover template noise. A filesystem scan found no `.env`, `.venv`, or cache directories left in the project folder, and a regex scan for key-shaped strings found nothing.

The only change outside the project folder is the single Directory Index row in `agents/README.md`: the `*(None yet)*` placeholder replaced by the `git-commit-assistant` row crediting `shraddhagavade`, which is exactly the one edit CONTRIBUTING allows. `git status` shows no other tracked modifications.

<details>
<summary>File map</summary>

Project files (all under `agents/git-commit-assistant/`):
- `main.py` — three-line entry shim delegating to `commit_assistant.cli.main`.
- `commit_assistant/__init__.py` — package docstring and version.
- `commit_assistant/diff_parser.py` — stdlib unified-diff parser → `DiffSummary`.
- `commit_assistant/message_builder.py` — deterministic mock heuristic and renderer.
- `commit_assistant/providers.py` — provider base, mock/openai providers, auto-selection, lazy openai import.
- `commit_assistant/cli.py` — argparse, diff acquisition, orchestration, exit codes.
- `tests/` — `conftest.py` plus `test_diff_parser.py`, `test_message_builder.py`, `test_providers.py`, `test_cli.py` and four `.diff` fixtures.
- `requirements.txt` — stdlib-only runtime note; `pytest==8.3.3` dev pin.
- `.env.example` — four project variables, all commented/documented.
- `.gitignore` — Python, secrets, env, and cache patterns.
- `README.md` — every section filled with real content.

Outside the folder:
- `agents/README.md` — single Directory Index row added for `git-commit-assistant`.

Full diff: `git diff main` (note project files are currently untracked; see `git status`).

</details>

</details>
