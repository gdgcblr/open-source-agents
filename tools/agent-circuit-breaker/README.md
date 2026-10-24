# Agent Circuit Breaker

> A dependency-free Python library and CLI that stops AI agents from looping on tool calls, burning through call budgets, or passing obvious secrets and dangerous arguments to tools.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Tool-using agents get stuck. They retry the same failing call, bounce between two tools forever (search → fetch → search → fetch), or keep going after every call errors. Each loop costs tokens, money and time, and an agent may also pass a `.env` path, an API key or `rm -rf` into a tool argument.
- **Intended Users**: Developers building agents with any framework (or none) who want a small, framework-agnostic check they can call before every tool execution, and reviewers who want to inspect a recorded tool-call trace for loops and leaks.

### Key Features
- **Loop detection**: blocks the Nth identical call (same tool + same arguments, key order ignored; default 3rd) and exact repeating cycles of 2–4 calls such as A → B → A → B.
- **Error and budget limits**: trips after N consecutive tool errors (default 3, reset by any success) and caps total calls per session (default 20).
- **Structured decisions**: every check returns `Decision(allowed, code, reason)` with `code` one of `ok`, `repeat`, `cycle`, `errors`, `budget`.
- **Secret redaction** (best-effort): replaces OpenAI-style `sk-…`, GitHub `ghp_…`/`gh?_…`, AWS `AKIA…` and bearer tokens with `[REDACTED:<label>]` in nested dicts/lists, including dict keys. Matched values are never printed.
- **Argument guardrails** (best-effort): flags `.env` file access (`.env.example` is allowed), `../` path traversal, and destructive commands (`rm -rf`, `mkfs`, `dd … of=/dev/…`, fork bombs, `format C:`, `del /s`, `shutdown`/`reboot` as commands, `DROP TABLE/DATABASE`).
- **CLI**: a `demo` that contrasts an unprotected and a protected run, and an `analyze` command that replays a JSONL trace.

---

## Technical Stack

- **Language & Runtime**: Python 3 (standard library only). Tested on Python 3.14.6 on Windows 11 only.
- **Agent Framework / Core Library**: Vanilla Python (`json`, `re`, `dataclasses`, `argparse`, `unittest`).
- **Models**: N/A. No LLM is called; the tool is model- and framework-agnostic.
- **External APIs / Tools**: None. No network access.

---

## Architecture & Data Flow

```
agent wants to call tool(args)
        |
        v
dlp.check_args(args) ----- hit -----> skip this call (guardrail)
        |
        v
CircuitBreaker.check(tool, args) -- blocked --> stop the agent (repeat / cycle / errors / budget)
        |
     allowed
        v
run the real tool  -->  CircuitBreaker.record_result(ok)
```

- `breaker.py`: `CircuitBreaker`, one instance per agent session (instances share no state). Calls are canonicalized as `tool:` + JSON with sorted keys. Blocked calls are not recorded and do not consume budget.
- `dlp.py`: `redact`, `redact_obj` and `check_args`. Kept separate from loop detection.
- `cli.py`: `demo`, `analyze` and `run_protected(script, execute)`, the guarded execution loop the demo uses.

---

## Prerequisites

- Python 3 (tested on 3.14.6; older Python 3 versions are untested)
- No packages, API keys or accounts

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/agent-circuit-breaker
   ```

2. **Install dependencies:** none. `requirements.txt` is intentionally empty apart from a comment (standard library only), so `pip install -r requirements.txt` is a no-op if you want to run it.

3. **Configure Environment Variables:** none required. `.env.example` exists only to follow the repository template.

---

## Configuration & Environment Variables

N/A. The tool reads no environment variables. Limits are constructor arguments:

| Argument | Default | Description |
| :--- | :--- | :--- |
| `max_repeats` | `3` | Block the Nth identical call in a session |
| `max_errors` | `3` | Block after this many consecutive errors |
| `max_calls` | `20` | Total allowed calls per session |
| `max_cycle_len` | `4` | Longest cycle period searched for |

---

## How to Run

```bash
# Simulated agent, unprotected vs protected (no real tools, no network)
python cli.py demo

# Replay a JSONL trace (exit code 0 = clean, 1 = issues found, 2 = file unreadable)
python cli.py analyze examples/sample_trace.jsonl

# Trace format help
python cli.py analyze --help
```

Using it as a library around your own tool executor:

```python
from breaker import CircuitBreaker
from dlp import check_args, redact_obj

breaker = CircuitBreaker(max_calls=20)

def guarded_call(tool, args):
    if check_args(args):
        return "blocked by guardrail"
    decision = breaker.check(tool, args)
    if not decision.allowed:
        raise RuntimeError(decision.reason)  # stop the agent loop
    try:
        result = run_tool(tool, args)  # your real tool
        breaker.record_result(True)
        return redact_obj(result)[0]  # redact secrets before returning
    except Exception:
        breaker.record_result(False)
        raise
```

### JSONL trace format

One JSON object per line; blank lines are ignored.

| Field | Type | Required | Meaning |
| :--- | :--- | :--- | :--- |
| `tool` | string | yes | Tool name |
| `args` | object | no | Tool arguments (default `{}`) |
| `session` | string | no | Session id; each gets its own breaker (default `"default"`) |
| `ok` | bool | no | Whether the call succeeded; feeds the consecutive-error counter |

Malformed or incomplete lines are reported as `MALFORMED` with a reason and line number, without echoing their content, and analysis continues.

**`analyze` is a replay, not a prevention.** It reports where the breaker *would* have blocked. The calls in a trace already happened, and nothing is undone.

---

## Example Input & Output

### Example Input
`python cli.py demo` runs a scripted agent that first tries to read `config/.env`, then loops `search` → `fetch` (the fetch always fails) 8 times.

### Example Output
Actual output (unprotected section shortened):
```
== Unprotected run ==
  #1  read_file ok
  #2  search    ok
  #3  fetch     ERROR
  ...
  #17 fetch     ERROR
  -> 17 calls executed, 8 failed, nothing stopped the loop

== Protected run (CircuitBreaker + guardrails) ==
  #1  read_file BLOCKED [guardrail] env_file_access
  #2  search    ok
  #3  fetch     ERROR
  #4  search    ok
  #5  fetch     BLOCKED [cycle] repeating cycle of 2 calls detected
  -> breaker tripped, agent halted
  -> 3 calls executed instead of 17
```

`python cli.py analyze examples/sample_trace.jsonl` (synthetic data, actual output):
```
line 1: [research] search {"q": "release notes"} -> allowed (call succeeded)
line 2: [research] fetch {"url": "https://example.invalid/notes"} -> allowed (call FAILED)
line 3: [research] search {"q": "release notes"} -> allowed (call succeeded)
line 4: [research] fetch {"url": "https://example.invalid/notes"} -> WOULD BLOCK [cycle] repeating cycle of 2 calls detected (call FAILED)
line 5: [ops] http_get {"headers": {"Authorization": "[REDACTED:bearer_token]"}} -> SECRETS bearer_token (call succeeded)
line 6: [ops] shell {"cmd": "cat ../.env"} -> GUARDRAIL env_file_access, path_traversal
line 7: MALFORMED invalid JSON (Expecting ',' delimiter at column 73)

Summary: 6 calls in 2 session(s), 1 would be blocked, 1 guardrail hits, 1 secrets redacted, 1 malformed lines
```

---

## How to Test

```bash
cd tools/agent-circuit-breaker
python -m unittest -v
```

51 `unittest` tests, standard library only, no network. They cover:
- the repeat, cycle, error and budget limits, tested at exactly their thresholds;
- argument normalization and session isolation;
- that the demo's protected loop never executes a blocked call;
- redaction in nested data and dict keys;
- guardrail hits, plus benign text that must not be flagged;
- malformed JSONL lines, including ones containing fake secrets, which must never be echoed.

All credentials in the tests are synthetic and built at runtime.

---

## Known Limitations

- **Best-effort, not a security boundary.** Redaction and guardrails are regular expressions. They miss encoded, split or unknown-format secrets and obfuscated commands, and a determined caller can bypass them. Use real sandboxing and least-privilege credentials.
- **Known false positives**: prose like "drop table tennis" is flagged as destructive, and "see ../README" is flagged as path traversal.
- **Exact matching only**: calls whose arguments vary slightly each time (e.g. a changing timestamp) are not seen as repeats or cycles. There is no fuzzy or semantic matching.
- **Cycle length**: cycles longer than `max_cycle_len` (default 4 calls) are not detected.
- **Repeat counting is per session, not consecutive**: A, B, A, C, A blocks at the third A.
- **Not thread-safe**: use one `CircuitBreaker` per session and don't share it across threads without your own locking.
- **`analyze` loads the whole file into memory.**
- **Tested only on Python 3.14.6 on Windows 11.** Other versions and platforms are untested.

---

## Security & Privacy Considerations

- **Secrets Handling**: The tool needs no credentials. `analyze` and `demo` print only redaction labels, never matched secret values, and malformed-line errors never include the line's content.
- **Data Privacy**: Everything runs locally. No data is sent anywhere.
- **Safety**: The tool never executes shell commands or real tools. The demo uses a simulated executor, and `analyze` only reads the given file.

---

## Future Improvements

- [ ] Optional normalization rules (e.g. ignore named volatile arguments) for near-duplicate detection.
- [ ] Streaming `analyze` for very large traces.
- [ ] More secret formats (e.g. Google API keys, Slack tokens).

---

## License

*This project is contributed under the repository's open-source license (MIT).*
