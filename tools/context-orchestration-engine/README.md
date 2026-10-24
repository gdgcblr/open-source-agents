# Monarch Memory: Context Orchestration Engine

> Context is infrastructure, not conversation: independent LLM workers finish one long task in sequence with zero raw conversation passed between them, each starting fresh from a compiled, token-budgeted briefing of engine-owned state.

---

## Overview

### Part of Monarch
Monarch is two projects in this repository that work as one:

| Part | Folder | What it is |
| :--- | :--- | :--- |
| **Monarch Memory** | `tools/context-orchestration-engine` (this folder) | The memory context engine. Works on its own with any LLM, through `python main.py` here. |
| **Monarch Team** | [`agents/engineering-team`](../../agents/engineering-team/) | Architect, Junior and Senior agents on Google ADK that clone a repository and fix a bug, sharing context only through this engine. One CLI: `python main.py` in that folder. |

How the shared context works:
- **State lives in the engine, not in a chat.** Objective, decisions with reasons, versioned artifacts, open issues, failed attempts, assumptions and handoff notes are typed records in SQLite.
- **The reconciler is the only writer.** Worker output is a claim. Provenance is stamped by the engine, fixes stay claims until verified, and failed attempts are never forgotten.
- **The compiler is the only reader workers see.** Each worker gets a fresh briefing built from that state under a token budget, ranked by relevance to its task, with founding decisions anchored.
- **Every turn is saved.** A killed run resumes from the last finished turn.

### Problem Statement & Intended Users
- **Problem**: When one LLM session hands work to another, the usual fix is to replay the whole conversation into the next model. That grows without bound, buries the details that matter, and ties the work to one session. Summaries are lossy in exactly the wrong places: decisions and their reasons, attempts that already failed, open problems, and the precise next action.
- **Intended Users**: Developers building multi-step or multi-model LLM pipelines who want handoffs between workers (different models, providers, keys or sessions) to be bounded, auditable and resumable.

### Key Features
- **Zero raw transfers**: every model call is exactly two messages, a fixed system prompt and one compiled briefing. A worker never sees another worker's reply. Each run reports `raw conversation transfers`, measured by checking every stored briefing for any earlier worker's verbatim reply.
- **State Reconciler (trust boundary)**: worker output is parsed as *claims*. The reconciler is the only writer of canonical state. It stamps provenance itself, records the step it assigned rather than the worker's wording, versions artifacts instead of overwriting them, keeps failed attempts append-only, and never closes an issue because a worker says it is fixed. The claimant is recorded and the issue stays open.
- **Context Compiler**: builds each briefing under a token budget (default 1,200), filling sections in a fixed priority order and ranking items by relevance to the assigned task, blended with recency, under a per-section cap. The earliest decisions and failed attempts are anchored so founding choices are never crowded out. Anything that does not fit is reported, not silently lost.
- **Gateways**: a deterministic offline mock (no keys, no network), a built-in standard-library HTTP gateway for any OpenAI-compatible `/chat/completions` endpoint, and optional LiteLLM (`COE_GATEWAY=litellm`).
- **Crash-safe persistence**: SQLite, committed after every turn. Kill the process mid-run and `--resume` continues from the last finished turn.
- **Reusable as shared memory**: [`agents/engineering-team`](../../agents/engineering-team/) imports this engine as the shared memory between three Google ADK agents (Architect, Junior, Senior). It plugs in its own gateway (one fresh ADK session per turn) without changing anything here.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+
- **Agent Framework / Core Library**: vanilla Python, with Pydantic v2 for every data contract. No agent framework.
- **Models**: any OpenAI-compatible chat endpoint: OpenAI, Groq, OpenRouter, Gemini (OpenAI-compatible API), Anthropic (OpenAI-compatible API), Ollama, or any URL you set as `api_base`. The packaged example roster uses five Groq-hosted models.
- **External APIs / Tools**: SQLite (standard library); optional LiteLLM.

---

## Architecture & Data Flow

```
                 objective + plan steps
                          |
                          v
                 +-----------------+        +------------------------+
                 |  Orchestrator   |<------>|  SQLite store          |
                 |  (sequential)   |  load/ |  state snapshot, brief-|
                 +-----------------+  save  |  ing, raw reply, report|
                    |           ^           |  committed every turn  |
     canonical      |           |           +------------------------+
     state          v           |
          +------------------+  |  ReconciliationReport
          | Context Compiler |  |  (warnings, rejected fixes, ...)
          | budget, priority,|  |
          | relevance, anchor|  |
          +------------------+  |
                    |           |
     ContextPackage |    +-----------------+
     (the briefing) |    | State Reconciler|  only writer of canonical state;
                    v    | claims -> facts |  stamps provenance, keeps issues open
          +------------------+    +-----------------+
          | Universal Worker |          ^
          | 2 messages only: |          | WorkerClaims + HandoffReport
          | system + briefing|----------+ (parsed JSON reply)
          +------------------+
                    |
                    v
          Gateway: Mock | HTTP (stdlib) | LiteLLM  -->  model provider
```

One turn: load state from SQLite -> compile a briefing for plan step *i* -> worker *i mod N* sends `[system, briefing]` -> reply is parsed into claims -> the reconciler merges claims into canonical state -> state, briefing, raw reply and report are committed in one transaction -> next worker.

| File | Role |
| :--- | :--- |
| `main.py` | Entry point: run, resume, inspect |
| `context_orchestration/contracts.py` | Claims vs canonical records, `ExecutionState`, `WorkerConfig` |
| `context_orchestration/reconciler.py` | The State Reconciler |
| `context_orchestration/compiler.py` | The Context Compiler and token estimator |
| `context_orchestration/worker.py` | The single worker class and the system prompt |
| `context_orchestration/gateway.py` | Mock, HTTP and LiteLLM gateways (the only module that knows providers exist) |
| `context_orchestration/orchestrator.py` | The loop, roster loading, transfer audit |
| `context_orchestration/store.py` | SQLite persistence and resume |
| `context_orchestration/demo.py` | The built-in five-step task and the mock's scripted replies |

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.11+
- pip
- For live runs only: an API key for each worker's provider (or a local OpenAI-compatible server such as Ollama). The offline mock needs no keys.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/context-orchestration-engine
   ```

2. **Set up the virtual environment / install dependencies:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Configure Environment Variables (live runs only):**
   ```bash
   cp .env.example .env                                   # then uncomment and fill in keys
   cp context_orchestration/workers.example.json workers.json   # then edit models if you like
   ```
   Without `workers.json`, the packaged example roster is used.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `WORKER_1_API_KEY` ... `WORKER_5_API_KEY` | Only for live runs | *None* | Keys for the example roster. Each worker in `workers.json` names its own variable via `api_key_env`, so these names are just the example's. |
| `COE_GATEWAY` | No | *unset* (built-in HTTP gateway) | Set to `litellm` to route live calls through LiteLLM (`pip install litellm` first). |

`workers.json` entries accept: `id`, `model` (`<provider>/<model id>`, e.g. `groq/openai/gpt-oss-120b`), `api_key_env` (or a literal `api_key`, never persisted), `api_base` (overrides the provider prefix, e.g. `http://localhost:11434/v1`), `temperature`, `max_tokens`, `max_retries`, `enabled`.

Command-line flags: `--objective`, `--task` (repeatable), `--resume TASK_ID`, `--state TASK_ID`, `--list`, `--stop-after N`, `--mock`, `--real`, `--budget N` (default 1200), `--db PATH` (default `orchestration.db`), `--workers PATH`, `--show-context`. Task IDs may be shortened to any unambiguous prefix.

---

## How to Run

```bash
# 1. Offline demo, no keys needed (falls back to the mock gateway automatically):
python main.py

# Print every briefing each worker received:
python main.py --mock --show-context

# Your own objective and plan:
python main.py --mock --objective "Design a notification service." \
  --task "Define requirements." --task "Design delivery." --task "Review the design."

# Stop part-way (or kill the process), then continue from SQLite:
python main.py --mock --stop-after 2
python main.py --resume <task_id>     # printed by the stopped run

# Inspect saved work:
python main.py --list
python main.py --state <task_id>

# 2. Live models: set keys in .env (and workers.json if you changed models), then:
python main.py --real
```

If any worker has no resolvable key, a run uses the mock unless you pass `--real`.

---

## Example Input & Output

### Example Input
```
python main.py
```
This runs the built-in objective, "Build the architecture and implementation plan for a Task Management REST API using FastAPI and PostgreSQL", as five plan steps across five workers.

### Example Output
Real output from the offline mock run (Windows 11, Python 3.12.2). The mock returns scripted replies, but compilation, reconciliation, persistence and the transfer audit all run for real.
```
No key for worker-1, worker-2, worker-3, worker-4, worker-5: using the offline MOCK gateway. Set keys in .env (see .env.example) and pass --real for live calls.
task-fbcb819e: Build the architecture and implementation plan for a Task Management REST API using FastAPI and PostgreSQL.

turn 1/5  worker-1  groq/openai/gpt-oss-120b
  task       Define the functional requirements and the overall system architecture for the API.
  briefing   58 of 1200 tokens, 2 sections, omitted: none
  reconciled +3 decisions, +2 artifacts, 0 versioned, +0 issues, +0 failed attempts

turn 2/5  worker-2  groq/qwen/qwen3.8-27b
  task       Continue from the current state and design the PostgreSQL database schema.
  briefing   308 of 1200 tokens, 10 sections, omitted: none
  reconciled +2 decisions, +2 artifacts, 1 versioned, +1 issues, +1 failed attempts
  warning    artifact 'erd.png' appears only in the handoff report

turn 3/5  worker-3  groq/openai/gpt-oss-20b
  task       Continue from the current state and design authentication and authorization.
  briefing   446 of 1200 tokens, 12 sections, omitted: none
  reconciled +2 decisions, +1 artifacts, 0 versioned, +1 issues, +1 failed attempts

turn 4/5  worker-4  groq/qwen/qwen3.6-27b
  task       Continue from the current state and design the REST API endpoints.
  briefing   560 of 1200 tokens, 12 sections, omitted: none
  reconciled +1 decisions, +1 artifacts, 1 versioned, +1 issues, +0 failed attempts

turn 5/5  worker-5  groq/openai/gpt-oss-120b
  task       Continue from the current state and review the complete architecture for inconsistencies and missing dependencies.
  briefing   643 of 1200 tokens, 12 sections, omitted: none
  reconciled +1 decisions, +1 artifacts, 0 versioned, +1 issues, +0 failed attempts
  warning    claimed completion of unplanned work, not recorded: 'Reviewed the architecture and fixed the refresh-token rotation issue.'
  warning    worker-5 claims I-2 is resolved; kept open until verified

task-fbcb819e  completed  (5/5 steps)
  workers used                5 (worker-1, worker-2, worker-3, worker-4, worker-5)
  raw conversation transfers  0
  peak briefing tokens        643
  decisions / artifacts       9 / 7 (artifacts unverified: content is not checked)
  open issues                 4
    I-1 [medium] Task ordering within a project is unspecified
    I-2 [high] Refresh-token rotation strategy unresolved (resolution claimed by worker-5, unverified)
    I-3 [medium] Bulk update transactional semantics undefined
    I-4 [high] Auth endpoints have no rate limiting
```

Excerpt of the briefing worker 5 actually received (`--show-context`). Worker 1's founding decisions reach worker 5 without any transcript:
```
YOUR ASSIGNED TASK
- Continue from the current state and review the complete architecture for inconsistencies and missing dependencies.

IMPORTANT DECISIONS
- Use FastAPI as the API framework. Reason: Async support and generated OpenAPI documentation
- Use PostgreSQL as the primary datastore. Reason: Relational task and user data with transactional integrity
- Use cursor-based pagination on list endpoints. Reason: Stable ordering under concurrent inserts
...
FAILED ATTEMPTS (DO NOT REPEAT)
- A single denormalised table for tasks and projects - Made per-project permission checks impossible to express
- Server-side sessions - Breaks under multiple instances without a shared store
...
NOTES FROM PREVIOUS WORKER (worker-4)
- Check the endpoints against the soft-delete decision.
```

Kill and resume (real run): the demo was hard-killed (`kill -9`, exit 137) after two turns had been committed. `--list` then showed `task-cce081b6  running  2/5`, and `python main.py --resume task-cce081b6` printed `resuming at step 3 of 5`, ran turns 3 to 5, and finished `completed (5/5 steps)` with `raw conversation transfers 0`.

Measured on the live demo run of the original project (real models, not this mock): 5 workers across 4 model families, 0 raw transfers, 1,199 peak tokens per handoff, about 90 seconds end to end. These figures were not re-measured on this build.

---

## How to Test

```bash
pip install -r requirements.txt
python -m pytest            # 56 tests, all offline: no keys, no network
python -m pyflakes context_orchestration tests main.py
```

Beyond unit coverage, the suite asserts the architectural claims directly:
- every model call is exactly `[system, briefing]`, and a full run has 0 raw transfers (the audit itself is tested against a deliberately leaked reply);
- a decision made by worker 1 reaches worker 5's briefing;
- a worker's "fixed it" claim leaves the issue open, and provenance a worker tries to self-report is ignored;
- briefings stay inside the budget as state grows, founding decisions survive 30 later ones, and dropped items are counted;
- 100 workers complete a 100-step plan with 0 transfers;
- a run that crashes at worker 4 resumes from SQLite in a fresh store and orchestrator, and worker 4's briefing is compiled from what was on disk;
- a literal API key never appears in the SQLite file;
- the HTTP gateway's request shape, retry on 429 (honouring `Retry-After`), and error messages that never echo the key.

Manual check: `python main.py` with no keys should end with `completed (5/5 steps)` and `raw conversation transfers 0`.

---

## Known Limitations

- **`verified` is always false.** Nothing inspects artifact content (no file checks, hashing or tool results), so every artifact is recorded and shown as `[unverified]`. Issues are therefore never closed automatically either. The field is where real validation would plug in.
- **Strictly sequential turns.** Plan step *i* goes to worker *i mod N*. No parallel workers, no cost-, capability- or rate-limit-aware switching. With more workers than steps, the surplus workers are not used.
- **Heuristic token estimate.** Budgets use `max(words, ceil(chars / 4))`, not a provider tokenizer (no tiktoken), so real token counts differ by model.
- **Not a tool-use runtime or scheduler.** Workers return text (JSON claims) only. They cannot call tools, run code or touch files, and there is no queueing, scheduling or concurrency.
- **Live path verified only with mocked HTTP in this build.** The test suite and the example above are offline. The HTTP gateway speaks OpenAI-compatible `/chat/completions` only; providers without such an endpoint need `api_base` pointing at a compatible proxy, or `COE_GATEWAY=litellm`.
- **Weak models may not return valid JSON.** A malformed reply is retried once with the same two messages, then the turn fails. The run stops there and can be resumed.
- **Free-tier rate limits.** Providers count `prompt + max_tokens` against per-minute limits. The gateway retries 429/5xx with backoff (up to `max_retries`, default 3), but a tight free tier can still exhaust them.
- **Tested on** Windows 11 with Python 3.12.2. Python 3.11 and Linux/macOS have not been run for this build.

---

## Security & Privacy Considerations

- **Secrets Handling**: keys come from environment variables (loaded from a local `.env` by python-dotenv), referenced per worker by `api_key_env`. A literal `api_key` in `workers.json` is allowed for local experiments, and `workers.json` is gitignored for that reason. Keys are excluded from every serialised model, never written to SQLite (a test checks the database file bytes), and never included in gateway error messages. `.env`, `workers.json` and `*.db` files are gitignored.
- **Data Privacy**: in live mode, each turn sends the system prompt and that turn's briefing (objective, plan step, and excerpts of canonical state: decisions, artifacts, issues, notes) to the provider configured for that worker. Requests carry the header `User-Agent: context-orchestration-engine/0.1`. Nothing is sent anywhere in mock mode. There is no telemetry, analytics or visit counting. All run data (state snapshots, briefings, raw model replies) stays in the local SQLite file you choose with `--db`; delete it to delete the history.
- **Safety**: the engine executes no shell commands and no model-generated code. Model replies are parsed as JSON data only.

---

## Future Improvements

- [ ] Real artifact verification (file existence, content hashes, tool results) so `verified` can become true and issues can be closed on evidence.
- [ ] Pluggable switching policies (cost-, capability-, rate-limit- and context-limit-aware).
- [ ] Optional provider-exact token counting.
- [ ] A live-model smoke test, run on demand with keys.

---

## License

This tool is released under the MIT License. See [`LICENSE`](LICENSE) (Copyright (c) 2026 Vivan Rajath), which is compatible with the repository's MIT license. It is a fresh, reduced build for this repository, based on the author's own project [context-orchestration-engine](https://github.com/VivanRajath/context-orchestration-engine).
