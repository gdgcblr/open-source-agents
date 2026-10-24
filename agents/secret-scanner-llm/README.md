# Secret Scanner (LLM-triaged, local Gemma)

> A secret scanner where deterministic detection finds candidates and a **local** Gemma model (via Ollama) triages them. Raw secrets are redacted before anything reaches the model, a log, or a report. Includes a Google ADK agent wrapper.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Regex-only secret scanners are noisy (placeholders, test fixtures, git SHAs, UUIDs, checksums), so people stop reading their output. Sending code to a hosted LLM to cut the noise is often not acceptable because the code contains the very secrets you are hunting.
- **Intended Users**: Developers and reviewers who want a pre-commit / CI-style secret check that runs fully on their machine, and people exploring local Gemma models for security triage.

### Key Features
- **Two-stage pipeline**: deterministic rules and entropy find candidates; a local Gemma model classifies each as `real`, `placeholder`, `test_fixture` or `false_positive`.
- **Redact-before-LLM**: only a short prefix, the length and the character shape of a value ever leave the detector, e.g. `sk_live_51H****(39 chars, base64-like)`. Tests prove raw values do not appear in prompts, logs, JSON, Markdown or exceptions.
- **Hard safety rule**: the LLM can never dismiss a known-format finding (AWS, GitHub, Stripe live, Google API, Slack, PEM private key) outside test paths. It can only add an explanation.
- **Graceful degradation**: clear errors when Ollama is down or the model is not pulled, plus a `--no-llm` mode; malformed model JSON is repaired or retried.
- **Practical scanning**: skips binaries, `.git`, `node_modules`, `.venv`, lockfiles and files over 1 MB; honours `.secretscanignore`; `--staged` scans the git index.
- **Google ADK wrapper** (`adk web` / `adk run`) with `scan_path` and `remediation_guide` tools, plus an eval set and smoke tests.
- **Benchmark harness** that generates a fixture of ~16 planted secrets and 15 decoys at runtime and compares `--no-llm` with any number of models.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+ (developed on 3.12)
- **Agent Framework / Core Library**: vanilla Python + `httpx` for the scanner; Google ADK 2.13.0 (`google-adk[extensions]`) for the agent wrapper
- **Models**: local Gemma via Ollama (default `gemma4:e2b-it-q4_K_M`; any Ollama model works for triage). The ADK chat agent additionally needs a model that supports tool calling (see Known Limitations).
- **External APIs / Tools**: Ollama HTTP API at `http://localhost:11434` (`/api/tags`, `/api/chat` with JSON-schema `format`); `git` (only for `--staged`). No cloud services or API keys.

---

## Architecture & Data Flow

```
                      STAGE 1: deterministic                       STAGE 2: local LLM
 file / dir / --staged ---------------------------+        +--------------------------------+
        |                                          v        |  Ollama  /api/chat             |
  skip rules (.git, node_modules,            detectors.py   |  temperature 0                 |
  .venv, lockfiles, binary, >1MB,            regex + entropy|  format = JSON schema          |
  .secretscanignore)                               |        |  {verdict, confidence,         |
                                                   v        |   reason, remediation}         |
                                         Candidate (REDACTED only:  ---->  prompt contains   |
                                         file, line, rule, kind,           ONLY redacted     |
                                         prefix+length+shape, context)     values            |
                                                   |        +---------------+----------------+
                                                   |                        | validate / repair / retry JSON
                                                   v                        v
                                      triage.py  SAFETY POLICY  <-----  TriageResult
                          known-format & non-test path  => always "real" (LLM can only explain)
                          low-confidence dismissal      => "uncertain" (still reported)
                          LLM down / --no-llm           => "unverified" (still reported)
                                                   |
                                                   v
                              report.py: Markdown / JSON  (+ remediation)   exit 1 if anything reportable

 ADK:  adk web / adk run --> root_agent (LiteLlm ollama_chat/<model>) --tools--> scan_path(), remediation_guide()
                                                                          \--> same scanner, same redaction
```

Design details (services and protocols, failure-mode table, guardrails, evaluation plan): **[docs/DESIGN.md](docs/DESIGN.md)**.

Package layout:

```
agents/secret-scanner-llm/
├── README.md  .env.example  .gitignore  .secretscanignore  pyproject.toml
├── secret_scanner/            # detectors, redaction, llm (Ollama), triage (policy), scanner, report, cli
├── secret_scanner_agent/      # ADK wrapper: __init__.py + agent.py (root_agent)
├── docs/DESIGN.md             # services, failure modes, guardrails, evaluation
├── tests/                     # pytest, Ollama mocked
├── eval/                      # ADK evalset + config + pytest smoke tests (+ live agent test)
└── benchmark/                 # runtime fixture generator, run_benchmark.py, results/
```

---

## Prerequisites

- Python 3.11 or newer (3.12 tested) and [`uv`](https://docs.astral.sh/uv/) (or plain `pip`)
- [Ollama](https://ollama.com) running locally, with at least one model pulled, e.g. `ollama pull gemma4:e2b-it-q4_K_M` (not needed for `--no-llm`, the unit tests, or the benchmark's `--no-llm` baseline)
- `git` (only for `--staged`)
- No API keys or paid services

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/secret-scanner-llm
   ```

2. **Create the virtual environment and install dependencies** (pinned in `pyproject.toml`):
   ```bash
   uv venv --python 3.12 .venv
   uv pip install --python .venv/bin/python -e ".[adk,dev]"
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   ```
   Scanner only (no ADK, smaller): `uv pip install -e ".[dev]"`. With plain pip: `python -m venv .venv && pip install -e ".[adk,dev]"`.

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Defaults work if Ollama listens on `localhost:11434`. The CLI reads real environment variables; `.env` is loaded automatically only by the ADK agent (export the variables yourself for the CLI).

4. **Pull a model** (not done by this project):
   ```bash
   ollama pull gemma4:e2b-it-q4_K_M
   ```

---

## Local Model Setup (Ollama + Gemma), step by step

The LLM triage and the ADK agent talk to a model running on your own machine through Ollama's HTTP API. Nothing is sent to a cloud service.

### 1. Install and start Ollama

```bash
# macOS (Homebrew)
brew install ollama
brew services start ollama        # runs the server in the background on :11434
# Linux:   curl -fsSL https://ollama.com/install.sh | sh
# Windows: installer from https://ollama.com/download
```

Check that the server is up:

```bash
curl http://localhost:11434/api/version
```

Stop it later with `brew services stop ollama`. Unload a model from memory with `ollama stop <tag>`.

### 2. Pick and pull a Gemma variant

Choose by your RAM. Sizes are the download sizes shown by `ollama list`; they are not a guarantee that a model fits next to your other apps.

| RAM | Suggested tag | Size | Notes |
|---|---|---|---|
| 8 GB | `gemma3:1b` | 0.8 GB | Not recommended: it dismissed 3 real secrets in our benchmark and has no tool calling, so it cannot drive the ADK agent. Use `--no-llm` on very small machines instead, or try `gemma4:e2b-it-q4_K_M` if it fits. |
| 8 to 16 GB | `gemma4:e2b-it-q4_K_M` | 4.6 GB | **Default.** 0 real secrets dismissed, about 1.5 s per candidate, supports tool calling (triage and the ADK agent). |
| 16 GB | `gemma4:e4b-it-q4_K_M` | 6.6 GB | Not recommended: it dismissed 1 real secret in our benchmark. |
| 16 GB+ | `gemma4:12b-it-q4_K_M` | 8.0 GB | Most precise (no false positives, 0 dismissed), about 8 s per candidate. |

```bash
ollama pull gemma4:e2b-it-q4_K_M
ollama list
```

These notes come from the benchmark in the Benchmark section (precision, recall, and the "real secrets wrongly dismissed" count, which must be 0).

> **Known issue (observed on Ollama 0.40.10, Homebrew, macOS arm64):** the *default* `gemma4:<size>` tags are MLX builds, and structured output failed with `structured output is unavailable`. This scanner needs structured output. Use the GGUF tags that end in `-it-q4_K_M` (as above). If you hit this error, run `ollama pull <tag>-it-q4_K_M` and set `OLLAMA_MODEL` to it. Only `gemma4:e2b` was confirmed broken; the other two default tags were not tested.

### 3. Check that the model has the capabilities you need

```bash
ollama show gemma4:e2b-it-q4_K_M
```

Look at the `Capabilities` list:
- `completion` is enough for the CLI triage.
- `tools` is **required for the ADK agent**. Models without it fail with `does not support tools`.

### 4. Point the project at your model

```bash
export OLLAMA_HOST=http://localhost:11434          # default, change if remote
export OLLAMA_MODEL=gemma4:e2b-it-q4_K_M           # used for triage
export OLLAMA_AGENT_MODEL=gemma4:e2b-it-q4_K_M     # used by the ADK chat agent (needs `tools`)
```

Or put the same lines in `.env` (`cp .env.example .env`). The ADK agent loads `.env` itself; for the CLI, export the variables in your shell.

### 5. Verify the integration

```bash
# 1) Pipeline without a model: should always work
python -m secret_scanner scan eval/sample_project --no-llm

# 2) Pipeline with the model: dismissed placeholders appear under "Dismissed by LLM triage"
python -m secret_scanner scan eval/sample_project --model "$OLLAMA_MODEL"

# 3) Fail-closed check: stop Ollama, rerun step 2. You should see a WARNING and
#    findings kept as "unverified" (never silently dropped).
brew services stop ollama
python -m secret_scanner scan eval/sample_project
brew services start ollama
```

If Ollama is down or the model is missing, the scanner warns and falls back to the deterministic result. Add `--require-llm` to make that case an error instead (exit code 2).

### 6. Run the ADK agent against your local model

```bash
adk web .                          # open http://localhost:8000, choose secret_scanner_agent
adk run secret_scanner_agent       # same agent in the terminal
```

Try: `Scan <absolute path to a folder> and tell me what to fix`. The agent can scan any local path. To confine it to one folder, set `SECRET_SCANNER_ROOT=/path/to/folder` before starting.

### 7. Compare models yourself (one at a time)

```bash
python benchmark/run_benchmark.py --models gemma4:e2b-it-q4_K_M
ollama stop gemma4:e2b-it-q4_K_M
python benchmark/run_benchmark.py --models gemma4:e4b-it-q4_K_M
```

Run models one at a time so they do not compete for memory and distort the latency numbers. Results are written to `benchmark/results/` and contain only redacted data.

### Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `connection refused` on port 11434 | Server not running: `brew services start ollama` (or `ollama serve`). |
| `model '<tag>' not found` | Not pulled: `ollama pull <tag>`, and check `OLLAMA_MODEL` spelling. The built-in default is `gemma4:e2b-it-q4_K_M`. |
| `structured output is unavailable` | You pulled an MLX default tag. Use a `-it-q4_K_M` tag. |
| `does not support tools` (ADK) | The chat model lacks the `tools` capability. Set `OLLAMA_AGENT_MODEL` to one that has it. |
| Very slow replies | Large model on a small machine, or thinking mode on. Try a smaller tag and close other apps. |
| `quote>` prompt in the shell | A stray `'` or `"` was pasted. Press `Ctrl+C` and retype the command. |

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `OLLAMA_HOST` | No | `http://localhost:11434` | Ollama server. Bare `host:port` forms are accepted. |
| `OLLAMA_MODEL` | No | `gemma4:e2b-it-q4_K_M` | Model used for triage (overridden by `--model`). Also the ADK chat model unless `OLLAMA_AGENT_MODEL` is set. |
| `OLLAMA_TIMEOUT` | No | `180` | Seconds per triage request. |
| `OLLAMA_API_BASE` | ADK only | `OLLAMA_HOST` (else `http://localhost:11434`) | Read by LiteLLM for the agent's chat model; set by `agent.py` if absent. |
| `OLLAMA_AGENT_MODEL` | No | `OLLAMA_MODEL` | Chat model for the ADK agent when it must differ from the triage model (it needs tool calling). |
| `SECRET_SCANNER_ROOT` | No | unset (any local path) | ADK agent only: if set, `scan_path` rejects paths that resolve (symlinks followed) outside this root. |
| `RUN_LIVE_AGENT_TESTS` | No | unset | Set to `1` to enable the live agent test in `eval/`. |

No secrets are required or stored.

---

## How to Run

### CLI

```bash
# Full pipeline (needs Ollama + a pulled model)
python -m secret_scanner scan path/to/repo

# Choose a model / host
python -m secret_scanner scan path/to/repo --model gemma4:12b-it-q4_K_M
OLLAMA_MODEL=gemma4:e2b-it-q4_K_M python -m secret_scanner scan .

# Deterministic only, no Ollama needed (everything is reported as "unverified")
python -m secret_scanner scan . --no-llm

# JSON output (still redacted) and git index only (e.g. in a pre-commit hook)
python -m secret_scanner scan . --json
python -m secret_scanner scan . --staged --no-llm
```

Exit codes (fail closed): `0` nothing reportable, `1` any non-dismissed finding (`real`, `uncertain`, or `unverified`), `2` usage/environment error or an incomplete scan with no findings. If Ollama is down or the model is not pulled, the scan **falls back to `--no-llm` with a visible warning** (nothing is silently passed); `--require-llm` exits 2 instead. `--max-llm-candidates N` caps LLM calls (rest reported as unverified).

Suppression: add patterns to `.secretscanignore` (`dir/`, `*.ext`, `path/glob`; no negation) or put `secretscan:ignore` in a line comment.

### Google ADK agent

Run from the project root (the folder that contains `secret_scanner_agent/`):

```bash
adk web .                      # then open http://localhost:8000 and pick "secret_scanner_agent"
adk run secret_scanner_agent   # terminal chat
```

The agent uses `LiteLlm(model="ollama_chat/<model>")` (the `ollama_chat/` prefix, not `ollama/`). **The chat model must support tool calling** (see Known Limitations). Example prompts: "Scan ./src for secrets" or "How do I fix a leaked github_token?".

### Choosing a Gemma variant

Use the benchmark results below, not guesses. Short version: `gemma4:e2b-it-q4_K_M` is the default (safe, fast, tool-capable); `gemma4:12b-it-q4_K_M` is the most precise but about 5x slower; `gemma3:1b` and `gemma4:e4b-it-q4_K_M` dismissed real secrets in our run and are not recommended.

Run `ollama show <model>` and look for `tools` in the capabilities before using a model as the ADK chat model.

---

## Example Input & Output

### Example Input

A one-file project (the token was assembled at runtime for this demo; it is not a real credential):

```python
import os

GITHUB_TOKEN = "<a 40-char ghp_ token>"
DB_PASSWORD = "changeme"
API_KEY = os.getenv("API_KEY")
```

```bash
python -m secret_scanner scan demo/ --model gemma3:1b
```

### Example Output

Genuine output from one run with `gemma3:1b` (a quick smoke test, not the benchmark; headings abbreviated by omitting the generic checklist):

```
# Secret scan report

- Mode: `llm` (model `gemma3:1b`)
- Files scanned: 1; candidates: 2; reported: 1; dismissed by triage: 1

## [CRITICAL] `app.py:3` - github_token

- Rule: `github_token`; value: `ghp_a1B****(40 chars, base64-like)`
- Verdict: **real** (confidence 0.95, decided by llm)
- Why: The code snippet clearly represents a GitHub token, which is a credential and should be rotated.
- Fix: Verify the token's security and rotate it immediately.

     1 | import os
     2 |
>    3 | GITHUB_TOKEN = "ghp_a1B****(40 chars, base64-like)"
     4 | DB_PASSWORD = "****(8 chars, alnum)"
     5 | API_KEY = os.getenv("API_KEY")

## Dismissed by LLM triage

- `app.py:4` quoted_credential_assignment -> placeholder (0.95): The code snippet contains a placeholder-like word ('changeme') and appears to be a dummy value intended for testing.
```

(The full report also lists the remediation checklist: rotate first, env var, `.env.example`, `.gitignore`, `git filter-repo`.) Exit code was `1`.

---

## How to Test

```bash
# Unit tests (Ollama mocked; no network, no model needed)
python -m pytest -q

# Import / CLI sanity checks
python -c "from secret_scanner_agent.agent import root_agent; print(root_agent.name)"
adk --help

# Deterministic baseline on the benchmark fixture (no Ollama needed)
python benchmark/run_benchmark.py

# Live ADK agent test (needs Ollama and a tool-calling-capable model)
OLLAMA_AGENT_MODEL=<tool-capable-model> RUN_LIVE_AGENT_TESTS=1 python -m pytest eval/test_agent_smoke.py -m live -s

# Prompt-injection tests (mocked, deterministic) and the real-model injection benchmark
python -m pytest tests/test_injection.py -q
python benchmark/run_benchmark.py --injection-only --models gemma4:e2b-it-q4_K_M

# ADK eval (5 cases, tool-trajectory only, no LLM judge; needs a tool-capable model; run from project root)
adk eval secret_scanner_agent eval/secret_scanner.evalset.json --config_file_path eval/test_config.json
```

The unit tests cover: detectors, redaction, no raw secret in prompts/logs/JSON/Markdown/exceptions, the safety policy (LLM cannot dismiss known-format findings), skip rules, `.secretscanignore`, `--staged`, JSON repair/retry, Ollama-down and model-missing errors. Test secrets are assembled from fragments at runtime; no realistic secrets are committed.

### Benchmark

`benchmark/run_benchmark.py` builds a fixture tree in a temp dir at runtime (16 planted secrets including obfuscated/custom formats and secrets in comments/shell scripts, one of them a deliberate hard miss; 15 decoys: placeholders, test fixtures, git SHA, UUID, digests, `os.getenv`, template variables), scans it with `--no-llm` and with each model in `--models`, and writes JSON + Markdown to `benchmark/results/`.

```bash
python benchmark/run_benchmark.py --models gemma4:e2b-it-q4_K_M
ollama stop gemma4:e2b-it-q4_K_M
python benchmark/run_benchmark.py --models gemma4:12b-it-q4_K_M
```

Run models one at a time so they do not compete for memory. Raw results are in `benchmark/results/`.

**Results**

| Config | Dismissed real (must be 0) | Precision | Recall | False positives (rate) | JSON valid | s/candidate | Total s |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `--no-llm` baseline | 0 | 0.62 | 0.95 | 11 (0.73) | n/a | 0 | 0.007 |
| `gemma3:1b` | **3** | 0.71 | 0.79 | 6 (0.40) | 1.00 | 1.09 | 31.8 |
| `gemma4:e2b-it-q4_K_M` (default) | 0 | 0.82 | 0.95 | 4 (0.27) | 1.00 | 1.45 | 42.1 |
| `gemma4:e4b-it-q4_K_M` | **1** | 0.94 | 0.90 | 1 (0.07) | 1.00 | 2.91 | 84.5 |
| `gemma4:12b-it-q4_K_M` | 0 | **1.00** | 0.95 | 0 (0.00) | 1.00 | 8.13 | 235.8 |

Measured on one machine (Apple M5, 16 GB, macOS, Ollama 0.40.10), one run per model with temperature 0, models run one at a time. The fixture is small (19 planted secrets, 15 decoys), so treat differences between models as indicative, not statistically established. One planted secret is a deliberate miss for every configuration.

How to read it:
- `gemma3:1b` and `gemma4:e4b` **fail the safety metric** (they dismissed 3 and 1 real secrets respectively) and should not be used as the triage model.
- `gemma4:e2b` is the default: zero real secrets dismissed, about 1.5 s per candidate, and it supports tool calling for the ADK agent. It still leaves 4 false positives.
- `gemma4:12b` had the best precision (no false positives) at about 8 s per candidate. Use it when you can accept the wait.
- The injection-only benchmark (`--injection-only`) has **not** been run against real models; only the mocked injection tests have.

A first run of the `gemma4` models gave almost all-malformed JSON (valid-JSON rate 0 to 2%, 17 to 77 s per candidate) and was discarded. Cause: Gemma 4 has thinking enabled by default and spent the 400-token output budget on reasoning. The client now sends `think: false`. Because every reply was unusable, the scanner kept all findings (fail-closed), which is the behaviour we want from a broken model.

---

## Known Limitations

- **Gemma and tool calling**: `gemma3:1b` has no tool support in Ollama, so it cannot drive the ADK agent (`does not support tools`). The `gemma4` GGUF builds report the `tools` capability and worked in `adk eval`. The scanner and its triage only need structured output.
- **Default `gemma4` Ollama tags may not work**: on Ollama 0.40.10 (Homebrew, macOS arm64) `gemma4:e2b` was an MLX build and structured output failed with `structured output is unavailable`. Use the `-it-q4_K_M` tags. Only `gemma4:e2b` was confirmed broken.
- **Thinking mode**: Gemma 4 reasons by default; the client sends `think: false` to keep replies within the output budget.
- **Small benchmark, one run per model, one machine**: results are indicative only. Small models over-dismiss non-known-format secrets (`gemma3:1b` dismissed 3, `gemma4:e4b` dismissed 1 real secret in our run); the safety rule protects only known-format findings.
- **ADK eval is 4 of 5 cases passing** with `gemma4:e2b-it-q4_K_M`: in `missing_path` the model added an extra `use_llm=False` argument and the strict trajectory match failed, although it answered correctly. Results vary by chat model and by run.
- **Prompt injection**: file content is fenced as untrusted data, and injection-looking text near a finding blocks any dismissal. The detector is regex-based, so a paraphrased attack could still sway the model for non-known-format findings. Known-format findings in non-test paths are immune.
- **Recall is bounded by the rules**: split or computed secrets (`a + b`), prose such as "the password is hunter2 (see wiki)", secrets only in binary/over-1MB/ignored files, and formats without a rule or enough entropy are missed. Secrets inside multi-line strings are only seen line by line.
- **Documentation keys are reported**: well-known example values in a non-test path (e.g. AWS's documented example key in `docs/`) match a known format and cannot be dismissed by the LLM. Put them under `tests/`/`fixtures/`, use `.secretscanignore`, or add `secretscan:ignore`.
- **Test-path heuristic**: paths under `test(s)/`, `__tests__/`, `spec/`, `fixtures/`, `testdata/`, `mocks/`, `e2e/`, or named `test_*`, `*_test.*`, `*.test.*`, `*.spec.*`, `conftest.py` allow the LLM to dismiss known-format findings at confidence >= 0.85. A real secret placed in such a path could be dismissed.
- **Context redaction is pattern-based**: neighbouring lines (+/- 2) go through the same detectors plus a long-opaque-token pass. A secret that no rule recognises can appear verbatim in the context sent to the (local) model. A short placeholder-vocabulary hint (words like `changeme`, `test`) is also sent so the model can recognise placeholders.
- **Reports are redacted but still reveal locations**: file paths, line numbers, variable names and value length/shape are included.
- **Scale**: triage is sequential (one request per candidate); large repos with many candidates are slow on bigger models. The benchmark's latency numbers depend on your hardware.
- **Platform**: developed and tested on macOS (Apple Silicon) with Python 3.12 only; Linux and Windows untested. `.secretscanignore` is a minimal matcher, not full gitignore semantics (no `!` negation).
- **ADK agent scans any local path** it is asked to; run it only on a machine and user account where that is acceptable.

---

## Security & Privacy Considerations

- **Secrets Handling**: the detector keeps raw values only transiently in memory inside `find_matches`; `Candidate`/`Finding` objects, prompts, logs, JSON/Markdown reports and exception messages contain only redacted forms. Tests assert this. No API keys are used. `.env` is gitignored; `.env.example` has placeholders only.
- **Data Privacy**: file content (redacted snippets) is sent only to the Ollama server you configure via `OLLAMA_HOST`, which defaults to localhost. If you point it at a remote host, redacted snippets and file paths go there. Nothing is sent to third parties by this project.
- **Safety**: the tool is read-only: it never modifies files, executes scanned code, or runs shell commands (except read-only `git` calls for `--staged`). The LLM output is parsed as data and cannot trigger actions. The LLM cannot override the known-format safety rule. The ADK agent's instruction forbids requesting, echoing or reconstructing raw secrets, but that is a prompt-level control on top of the code-level redaction in the tools.

---

## Future Improvements

- [ ] Run the injection benchmark against real models and enlarge the fixture.
- [ ] Verify the ADK agent end to end with a tool-calling-capable local model (or add a prompt-based tool fallback for Gemma builds without native tools).
- [ ] Batch several candidates per LLM call and cache verdicts by (rule, redacted context).
- [ ] Add `git log -p` / history scanning and a baseline file for known findings.
- [ ] More rules (cloud providers, Twilio, SendGrid, npm, etc.) and multi-line context handling.
- [ ] SARIF output and a ready-made pre-commit hook.

---

## License

*This project is contributed under the repository's open-source license.*
