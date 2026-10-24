# git-commit-assistant

> A Python CLI agent that reads your staged git diff and writes a Conventional Commits message for you — fully offline by default, with an optional OpenAI mode.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Writing consistent, well-formed [Conventional Commits](https://www.conventionalcommits.org/) messages is tedious and easy to get wrong. Teams want a predictable `type(scope): summary` format with a useful body, but authoring it by hand for every commit slows people down.
- **Intended Users**: Developers and teams who stage changes with `git add` and want a sensible commit message drafted automatically, including in CI or on machines with no LLM API key.

### Key Features
- **Offline by default**: a deterministic `mock` provider inspects the diff (files changed, added/removed lines, extensions, add/delete/modify/rename) and produces a Conventional Commits message with zero network calls and zero config.
- **Optional OpenAI mode**: set `OPENAI_API_KEY` to draft messages with an LLM. The `openai` package is imported lazily, so it is never needed for the default path.
- **Auto provider selection**: picks `openai` when a key is present and the SDK is installed, otherwise falls back to `mock`. An explicit `--provider` always wins.
- **Flexible input**: reads `git diff --staged`, or any diff file via `--diff-file` for demos and tests.
- **Friendly failures**: clear messages and handled exit codes when git is missing, nothing is staged, or a config is wrong.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+ (standard library only for the default path).
- **Core Library**: none required for `mock` — pure stdlib (`argparse`, `subprocess`, `dataclasses`).
- **Models**: optional OpenAI chat completions (e.g. `gpt-4o-mini`) via the `openai` SDK.
- **External APIs / Tools**: `git` (for reading the staged diff); OpenAI API (optional).

---

## Architecture & Data Flow

The flow is a straight pipeline. The CLI acquires diff text (from git or a file), a provider turns it into a message, and the message is printed.

```
[git diff --staged]                      cli.read_staged_diff()
        or              --> diff text --> providers.resolve_provider()
[--diff-file PATH]                                 |
                                   +---------------+---------------+
                                   |                               |
                            MockProvider                    OpenAIProvider
                   diff_parser.parse_diff()            lazy import openai
                   message_builder.build_message()     chat.completions
                   message_builder.render()                   |
                                   |                           |
                                   +-----------> commit message text -----------> stdout
```

Module responsibilities:
- `commit_assistant/diff_parser.py` — pure parser: unified diff text -> `DiffSummary` of `FileChange` records. No I/O.
- `commit_assistant/message_builder.py` — the deterministic heuristic: `DiffSummary` -> `CommitMessage` -> rendered text.
- `commit_assistant/providers.py` — `MockProvider`, `OpenAIProvider` (lazy import), auto-selection, and errors.
- `commit_assistant/cli.py` — argument parsing, diff acquisition, orchestration, exit codes.
- `main.py` — thin entry point.

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.10 or newer.
- `pip` (for installing the optional dev/test dependency).
- `git` on your PATH — only needed when reading real staged changes (not for `--diff-file`).
- An OpenAI API key — **optional**, only for the `openai` provider.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/git-commit-assistant
   ```

2. **Set up a virtual environment and install dependencies:**

   Windows (PowerShell):
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

   Linux / macOS:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

   The default `mock` provider needs no third-party packages at all; `requirements.txt` only pins `pytest` for running the test suite. To use the OpenAI provider, additionally run `pip install openai`.

3. **(Optional) Configure environment variables:**
   ```bash
   cp .env.example .env    # Windows PowerShell: Copy-Item .env.example .env
   ```
   Leave it untouched to run fully offline.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `OPENAI_API_KEY` | No | *None* | OpenAI API key. When set (and `openai` installed), `--provider auto` selects the `openai` provider. |
| `GEMINI_API_KEY` | No | *None* | Reserved for a future Gemini provider; currently unused. |
| `PROVIDER` | No | `auto` | Default provider when `--provider` is omitted. One of `auto`, `mock`, `openai`. |
| `MODEL_NAME` | No | `gpt-4o-mini` | Model name for the `openai` provider. Ignored by `mock`. |

Never commit real secrets. The `.env` file is git-ignored.

---

## How to Run

From the project directory (`agents/git-commit-assistant`):

```bash
# Stage some changes first, then draft a message from the staged diff:
python main.py

# Force the offline heuristic:
python main.py --provider mock

# Read a diff from a file instead of git (great for demos/tests):
python main.py --diff-file tests/fixtures/add_module.diff

# Header line only, no body:
python main.py --no-body

# Use OpenAI (requires OPENAI_API_KEY and `pip install openai`):
python main.py --provider openai --model gpt-4o-mini
```

CLI flags:
- `--provider {auto,mock,openai}` — provider to use (default `auto`).
- `--diff-file PATH` — read the diff from a file instead of running git.
- `--model NAME` — model override (openai only; ignored by mock).
- `--no-body` — print only the header line.
- `--help` — full usage.

Exit codes: `0` success, `1` no staged changes / empty diff, `2` git missing, unreadable diff file, or provider/config error.

---

## Example Input & Output

Captured from a real `mock`-mode run on this repository (no API key, no network):

### Example Input
```
python main.py --diff-file tests/fixtures/add_module.diff --provider mock
```

The fixture `tests/fixtures/add_module.diff` adds a new file `commit_assistant/greet.py` (+6 lines).

### Example Output
```
feat(commit_assistant): add greet module

- add commit_assistant/greet.py (+6/-0)
```

Another real run against a docs-only change (`tests/fixtures/docs_only.diff`):
```
docs(README): update README.md documentation

- update README.md (+2/-0)
```

---

## How to Test

From the project directory:

```bash
# Install the test dependency if you have not already:
python -m pip install pytest

# Run the suite (no git, no network required):
python -m pytest -q
```

The suite covers the diff parser, the mock heuristic, provider resolution across flag/env/key combinations, and the CLI via `--diff-file`. All fixtures are checked-in `.diff` files, so tests never call real git or the network.

---

## Known Limitations

- The `mock` provider is a **heuristic, not a semantic analysis**: it reasons about file paths, extensions, and line counts, not the meaning of the code. It will not always pick the "perfect" type or summary, but it is deterministic and reproducible.
- The `openai` provider is **not exercised in automated tests** (that would require a real key and network); only its missing-key / missing-package error paths are tested.
- Verified on Windows (PowerShell) with Python 3.12. The code targets 3.10+ and standard POSIX shells; it has not been run on every platform.
- Diff parsing targets standard `git diff` unified output. Exotic or binary diffs are summarised conservatively.

---

## Security & Privacy Considerations

- **Secrets Handling**: no secrets are required for the default path. `OPENAI_API_KEY` is read from the environment only; it is never logged or written to disk. `.env` is git-ignored.
- **Data Privacy**: the `mock` provider sends **nothing** off your machine — all processing is local. The `openai` provider transmits your staged diff to the OpenAI API to generate a message; do not use it on diffs you cannot share with a third party.
- **Safety**: the tool runs exactly one external command, `git diff --staged`, with a fixed argument list (no shell interpolation of user input). It does not execute code from the diff and makes no other process calls.

---

## Future Improvements

- [ ] Add a `gemini` provider behind `GEMINI_API_KEY`.
- [ ] Support local models (e.g. via Ollama) for private LLM drafting.
- [ ] Optional commit-scope configuration and custom type rules.
- [ ] A `--write` mode to pipe the message straight into `git commit`.

---

## License

This project is contributed under the repository's open-source license.
