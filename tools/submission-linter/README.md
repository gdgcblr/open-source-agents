# submission-linter

> A pre-flight checker that runs this repository's contribution rules on your project folder in seconds, so you find leaked keys, unfilled templates and broken run commands before a maintainer does.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Community repositories receive many pull requests, and most review time goes on mechanical problems rather than on the idea: an API key committed by accident, a README that is still the template, run commands that point to files that do not exist, environment variables the code reads but nobody documented, a committed `.venv/`, or a PR that also touches files outside the project folder. Contributors hit these blind, and maintainers catch them by hand, slowly and inconsistently.
- **Intended Users**:
  - *Contributors* (including first-time open-source contributors at hackathons): run it before `git push` and fix everything it reports.
  - *Maintainers*: use it as a shared, objective pass/fail standard, locally or in CI.

### Key Features
- **Repo-rule checks**: location (`agents/` or `tools/`), kebab-case and non-generic name, required files, dependency manifest, all README sections from the template.
- **Template leftovers**: detects text copied verbatim from `template/README.md` (the bracketed title and summary, the sample limitations, the sample `main.py --query` command, and so on).
- **Secret scan**: provider key formats (AWS, Google, OpenAI, Anthropic, GitHub, Slack, Hugging Face), private keys and high-entropy `*_KEY = "..."` assignments. Findings are redacted in the output. It only looks at files git would commit, so a correctly ignored `.env` is not a false alarm.
- **Reproducibility checks**: every environment variable read in code must appear in `.env.example` and the README; every Python import must be declared in `requirements.txt` / `pyproject.toml`; every `python`, `node`, `npm run` or `streamlit run` command in "How to Run" and "How to Test" must point to something that exists.
- **PR scope check**: errors when your branch changes files outside your project folder (the one allowed exception is the index row in `agents/README.md` or `tools/README.md`).
- **Optional LLM review (`--llm`)**: asks a model (local Ollama by default) whether the README is honest about what the code does, for example undisclosed shell execution or network calls. These findings are advisory only and never fail the run.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+ (standard library only at runtime)
- **Agent Framework / Core Library**: Vanilla script. No framework; the LLM pass is a plain HTTP call to an OpenAI-compatible `/chat/completions` endpoint.
- **Models**: None for the core checks. Optional: any OpenAI-compatible model (default `llama3.1` through Ollama).
- **External APIs / Tools**: `git` (for file listing and the scope check); the LLM endpoint only if you pass `--llm`.

---

## Architecture & Data Flow

```
project dir ──> list_files (git-aware) ──> checks ──────────────┐
                                           ├ location / names   │
                                           ├ required files     ├─> Report ──> text / JSON ──> exit code
                                           ├ README structure   │
                                           ├ secret scan        │
                                           ├ env + dependency   │
                                           ├ run commands       │
                                           └ PR scope (git diff)│
                                                                │
README + clean source files ──(only with --llm)──> LLM ─────────┘  (advisory findings)
```

The deterministic checks decide pass or fail. The LLM pass receives only the README and source files that contain no detected secret (never `.env*` files), is capped at about 32k characters, and can only add `warn`/`info` findings.

---

## Prerequisites

- Python 3.10 or newer
- `pip` (only needed to install the test dependency)
- `git` on your `PATH`
- Optional, for `--llm`: a running Ollama server (`ollama serve`, then `ollama pull llama3.1`) or an API key for any OpenAI-compatible provider

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/submission-linter
   ```

2. **Install dependencies** (only `pytest`, used by the test suite; running the linter needs nothing):
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Configure environment variables** (only for `--llm`):
   ```bash
   cp .env.example .env
   ```
   The tool reads real environment variables; it does not load `.env` by itself, so export them in your shell (for example `export $(grep -v '^#' .env | xargs)`).

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `LLM_BASE_URL` | No | `http://localhost:11434/v1` | OpenAI-compatible base URL used by `--llm` (Ollama by default) |
| `LLM_API_KEY` | No | `ollama` | API key sent as a Bearer token; Ollama ignores it, hosted providers need a real one |
| `LLM_MODEL` | No | `llama3.1` | Model name understood by the endpoint |
| `NO_COLOR` | No | *unset* | Set to any value to disable coloured output |

---

## How to Run

From `tools/submission-linter`, point it at the project you want to check:

```bash
python -m submission_linter ../../agents/<your-project-slug>
```

Useful flags:

```bash
python -m submission_linter . --json            # machine-readable output for CI
python -m submission_linter . --strict          # warnings also fail the run
python -m submission_linter . --base upstream/main   # branch to compare for the PR scope check
python -m submission_linter . --llm-dry-run     # show exactly which files --llm would send
python -m submission_linter . --llm             # add the advisory LLM review
```

Exit codes: `0` pass, `1` errors found (or warnings with `--strict`), `2` the path is not a directory.

---

## Example Input & Output

### Example Input
A deliberately broken project: generic directory name, template README left in place, a hard-coded AWS-style key, an undeclared `numpy` import, and a run command for a file that does not exist.

```bash
python -m submission_linter agents/my-agent --no-color
```

### Example Output
Real output from that run (the `DOC001` template-text finding, hints and file locations are omitted for space; the tool prints them under each finding):

```
ERROR DOC003  README is missing 9 required section(s): Overview (Problem Statement & Intended Users); Technical Stack; Prerequisites; Installation & Setup; Configuration & Environment Variables; Example Input & Output; How to Test; Known Limitations; Security & Privacy Considerations
ERROR FIL001  Missing required file: .env.example
ERROR FIL001  Missing required file: .gitignore
ERROR LOC003  Directory name 'my-agent' is too generic.
ERROR RUN001  README runs `python app.py` but 'app.py' does not exist in the project.
ERROR SEC001  Possible secret: AWS access key ID (AKIA…)
WARN  DEP001  'numpy' is imported but not declared in the dependency manifest.
WARN  DOC005  README has no 'Architecture & Data Flow' section.
WARN  DOC005  README has no 'Future Improvements' section.
WARN  DOC005  README has no 'License' section.
WARN  ENV002  MODEL_NAME is read in code but not documented in the README.
INFO  SCP000  Not inside a git repository; PR scope check skipped.

7 error(s), 5 warning(s), 1 note(s)
Result: FAIL — fix the errors before opening a PR.
```

---

## How to Test

```bash
python -m pytest
```

The suite (23 tests) builds throwaway projects and git repositories in a temp directory and covers naming, missing files, untouched templates, secrets (including redaction and the allow marker), env and dependency drift, run-command validation, PR scope, and the LLM path with an injected fake transport. It needs no network and no model.

To check the tool on itself:

```bash
python -m submission_linter . --strict
```

---

## Known Limitations

- Tested on Linux with Python 3.13 only; macOS and Windows are untested.
- The LLM review has been tested only against a fake transport in the test suite, not against a live Ollama or hosted model, so prompt quality and the JSON-parsing fallback with real models are unverified. Small local models may return malformed JSON; the tool then reports a note and moves on.
- Dependency checking covers Python imports only. JavaScript, Go and Rust dependencies are not cross-checked against their manifests.
- Environment variable detection uses regular expressions for common patterns (`os.getenv`, `os.environ`, `process.env`, `os.Getenv`, `env::var`); dynamic names are not found.
- Run-command validation understands `python`, `node`/`tsx`/`ts-node`/`bun`, `streamlit run` and `npm`/`pnpm`/`yarn` scripts. Other launchers are not verified, and it checks that targets exist, not that they run successfully.
- The secret scan is heuristic: it can miss unusual formats and occasionally flag test fixtures (add `# lint:allow-secret` on the line). It is a safety net, not a substitute for rotating a key that was ever committed.
- Section detection is keyword-based on README headings; unusual wording of a heading may be reported as missing.
- The PR scope check needs a base ref such as `upstream/main`; without one it is skipped with a note.

---

## Security & Privacy Considerations

- **Secrets Handling**: The tool needs no credentials unless you use `--llm`. `LLM_API_KEY` is read from the environment, sent only to the endpoint you configure, and never printed. Detected secrets are redacted to their first four characters in all output.
- **Data Privacy**: Without `--llm` nothing leaves your machine. With `--llm`, the README and source files (up to about 32k characters) are sent to `LLM_BASE_URL`. Files containing a detected secret and any `.env*` file are never sent. Run `--llm-dry-run` first to see the exact list. Use a local Ollama endpoint if the code is private.
- **Safety**: Read-only. It never executes the project's code and never modifies files. It runs a few read-only `git` commands (`rev-parse`, `ls-files`, `diff`, `status`). LLM output is treated as untrusted text: it is parsed as JSON, capped at 8 findings, and can only produce advisory findings.

---

## Future Improvements

- [ ] Cross-check JavaScript/TypeScript, Go and Rust dependencies against their manifests.
- [ ] Ship a ready-made GitHub Actions workflow so maintainers can run it on every PR.
- [ ] Verify that the index row in `agents/README.md` / `tools/README.md` was added and is well-formed.
- [ ] Add `--fix` for safe repairs (for example copying missing template files).

---

## License

This project is contributed under the repository's open-source license.
