# AgentGuard

> A dependency-free Python CLI that flags common reliability and security footguns in AI-agent projects. Runs entirely locally: no LLM calls, no uploaded source code.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: AI-agent codebases often contain subtle reliability and security footguns — hardcoded API keys, network calls with no timeout, `eval`/`exec` of untrusted strings, unbounded loops — that are easy to miss in a normal code review.
- **Intended Users**: Developers and reviewers who want a fast, local, zero-dependency sanity check on an agent project before committing or shipping it.

### Key Features
| Rule | Severity | What it flags |
| :--- | :--- | :--- |
| AG001 / AG002 | High | Likely hardcoded API credentials or provider-style keys |
| AG101 | Medium | `requests.*` calls without an explicit timeout |
| AG102 | Low | `while True` loops that may need a bounded exit strategy |
| AG201 | High | Calls to `eval()` or `exec()` |
| AG301 | Low | Agent/tool/run/execute functions without docstrings |
| AG000 | Info | Python syntax errors that prevent structural checks |

Findings are heuristics, not proof of a vulnerability — `while True` may be intentional, and credential patterns can produce false positives or miss real secrets. Every finding should be reviewed manually.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: Vanilla script using only the Python standard library (`ast`, `re`, `argparse`, `json`) — no agent framework, no third-party dependencies
- **Models**: None. This is a purely static analyzer; it never calls an LLM.
- **External APIs / Tools**: None

---

## Architecture & Data Flow

```
[target directory] --> [walk files, skip .git/.venv/venv/node_modules/__pycache__/.tox/dist/build]
                                          |
                        +-----------------+-----------------+
                        |                                   |
          [regex secret-pattern scan]          [Python AST walk: requests timeout,
                        |                        eval/exec, while True, docstrings]
                        +-----------------+-----------------+
                                          |
                                  [Finding list, deduped]
                                          |
                            [text report]  or  [JSON report]
```

---

## Prerequisites

- Python 3.10 or newer
- No third-party runtime dependencies (no `pip install` required to run the scanner itself)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/agentguard
   ```

2. **Dependencies**: none to install for running the tool. If you want to run the test suite, no extra packages are needed either — it uses `unittest` from the standard library.

3. **Environment variables**: N/A — AgentGuard does not read any API keys or environment variables. `.env.example` documents this explicitly.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| *(none)* | — | — | AgentGuard takes no environment variables or API keys. |

---

## How to Run

```bash
python agentguard.py /path/to/project
python agentguard.py . --format json
python agentguard.py . --fail-on medium
```

`--fail-on` is useful in CI: it returns exit code `1` when a finding at the selected severity or higher is present. The default (`never`) is informational and always exits `0` after a valid scan.

---

## Example Input & Output

### Example Input
```bash
$ python agentguard.py . --format text
```
(run against a sample file containing a hardcoded key, an undocumented `run_agent` function, and a `while True` loop)

### Example Output
```
AgentGuard report — /path/to/project
Findings: 4 | HIGH 2 · MEDIUM 0 · LOW 2 · INFO 0

[HIGH] AG001 sample.py:1 — Possible hardcoded credential
  Fix: Read credentials from environment variables or a secret manager; rotate exposed keys.
[HIGH] AG002 sample.py:1 — Possible provider API key in source
  Fix: Remove the key from source history and rotate it immediately.
[LOW] AG301 sample.py:3 — Function 'run_agent' has no docstring.
  Fix: Document expected inputs, side effects, failure modes, and whether the function can access external systems.
[LOW] AG102 sample.py:4 — Unconditional while True loop may run indefinitely.
  Fix: Ensure the loop has a clear stop condition, iteration budget, cancellation path, or timeout.
```

This exact output was reproduced while reviewing this contribution, confirming all four rule categories fire as documented.

---

## How to Test

From this directory:
```bash
python -m unittest discover -s tests -v
```

The included suite (`tests/test_agentguard.py`) has 4 tests covering: detecting a missing-timeout request, accepting a request that has a timeout, detecting `eval`/`exec`, and confirming `.venv`/virtual-env directories are skipped. All 4 pass as of this review.

---

## Known Limitations

- Findings are heuristics, not guarantees: credential-pattern matching can both false-positive (e.g. a long random-looking string that isn't a key) and miss real secrets in unrecognized formats.
- `while True` is flagged unconditionally; many such loops are intentional (e.g. a long-running agent's main loop) and the finding is advisory only.
- Only Python files receive AST-based checks (timeout, eval/exec, loop, docstring rules); the credential-pattern scan runs across all readable text files regardless of language.
- Not a replacement for code review, dedicated secret scanning, dependency auditing, or runtime tests — it covers a small, fixed rule set.

---

## Security & Privacy Considerations

- **Secrets Handling**: AgentGuard itself needs no credentials; it only reads files to look for *other* projects' exposed secrets. `.env.example` documents that no variables are required.
- **Data Privacy**: Everything runs locally. The tool reads text files under the target directory and never transmits file contents anywhere. It explicitly skips `.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `.tox`, `dist`, and `build`.
- **Safety**: AgentGuard never executes, imports, or evaluates the code it scans — it only parses Python source into an AST and applies regex patterns to text.

---

## Future Improvements

- [ ] Expand the secret-pattern list and allow a project-level custom pattern/allowlist file.
- [ ] Add checks for additional languages beyond Python (the credential scan already covers any text file; AST-based checks are Python-only).
- [ ] Optional SARIF output for GitHub code-scanning integration.

---

## License

This project is contributed under the repository's open-source license (MIT).
