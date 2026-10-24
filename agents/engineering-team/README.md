# Monarch: Engineering Team (Architect, Junior, Senior on Google ADK)

> Point Monarch at a repository and a bug, and three separate Google ADK agents (an Architect, a Junior Engineer and a Senior Engineer) investigate, fix and review it. They hand work to each other only through Monarch's shared memory, the [context-orchestration-engine](../../tools/context-orchestration-engine/), never through shared conversation.

---

## Overview

### What is Monarch?
Monarch is two projects in this repository that work as one:

| Part | Folder | What it is |
| :--- | :--- | :--- |
| **Monarch Memory** | [`tools/context-orchestration-engine`](../../tools/context-orchestration-engine/) | The memory context engine: engine-owned shared state, a reconciler, a context compiler and SQLite persistence. Usable on its own with any LLM. |
| **Monarch Team** | `agents/engineering-team` (this folder) | Three Google ADK agents that use Monarch Memory as their only channel to each other, behind one CLI: `python main.py`. |

**Context is infrastructure, not conversation.** In most multi-agent setups, the next agent receives the previous agent's chat. In Monarch, no agent ever sees another agent's words. Instead:

1. **One shared memory.** The task's state (objective, decisions and their reasons, artifacts and versions, open issues, failed attempts, assumptions, notes for the next agent) lives in Monarch Memory, in SQLite.
2. **One writer.** An agent's reply is treated as *claims*. The State Reconciler is the only thing that writes shared memory: it stamps who said what, versions files instead of overwriting them, keeps failed attempts forever, and never closes an issue just because an agent says it is fixed.
3. **A compiled briefing per turn.** Before each agent runs, the Context Compiler reads shared memory and builds a briefing under a token budget. Sections are filled by priority, items are ranked by relevance to that agent's task, and the founding decisions are always kept. The agent starts in a brand-new ADK session holding only that briefing.
4. **Saved after every turn.** Every turn is committed to SQLite, so a crashed or rate-limited run resumes where it stopped, and `python main.py memory <task>` shows exactly what the team knows and who contributed each piece.

```
Architect --claims--> Reconciler --> SHARED MEMORY --> Compiler --briefing--> Junior
Junior    --claims--> Reconciler --> SHARED MEMORY --> Compiler --briefing--> Senior   ... and so on
```

Quick start (offline, no key needed):
```bash
cd agents/engineering-team
python -m venv .venv && .venv\Scripts\activate      # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python main.py                                        # opens the Monarch CLI
```

### Problem Statement & Intended Users
- **Problem**: multi-agent pipelines usually hand off by sharing one growing conversation or session. Every agent then sees everything every other agent said: context grows without bound, roles blur (a reviewer rewrites code, an implementer quietly changes the design), and one agent's claims ("fixed it", "wrote the file") become everyone's facts.
- **Intended Users**: developers who want a role-based agent team on Google ADK that works on real repositories, with strict role separation, bounded context per agent, guardrails enforced in code, and a record of who claimed what.

### Key Features
- **One entry point, one CLI**: `python main.py` opens an interactive prompt. Type `clone https://github.com/owner/repo and fix: <bug>`, or `build <something>`.
- **Clone and fix**: the repository is shallow-cloned into a task workspace. The Architect reads the code and records the root cause and fix; the Junior writes the fix and a test; the Senior reviews the actual `git diff`. The result is saved as a `.patch` file. Nothing from the cloned repository is ever executed.
- **Three independent ADK agents**: `architect_agent/`, `jnr_agent/` and `snr_agent/` are separate ADK agent packages, each with its own persona, tools, guardrail policy and `root_agent`. None imports another, and a test checks that.
- **Shared memory, not shared chat**: every handoff goes through the [context-orchestration-engine](../../tools/context-orchestration-engine/). Its reconciler is the only writer of the team's state, and each agent turn starts in a brand-new ADK session (`include_contents="none"`) holding one compiled, token-budgeted briefing. Runs report `raw conversation transfers: 0`, measured from what was actually sent. `python main.py memory <task>` shows the shared memory with provenance.
- **Guardrails in ADK callbacks, not just prompts**:
  - The request and the repository source are screened. Only `https://` or a local folder may be cloned; `ssh`, `ext::` and `file::` are refused.
  - Every briefing is scanned for prompt injection before the model is called.
  - Secrets are redacted from replies.
  - A Junior's design decisions become issues for the Architect, and the Architect cannot mark issues resolved.
  - A Junior's claim about a file it never wrote becomes a high-severity issue.
  - A Senior cannot claim artifacts.
  - Only the Junior can write, inside the task folder, never into `.git`.
- **Offline mock and resume**: a scripted ADK `BaseLlm` runs everything through real ADK sessions, callbacks and tools with no key. Every turn is committed to SQLite, so a stopped or failed run resumes.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+ (google-adk 2.13.0 requires 3.11+)
- **Agent Framework / Core Library**: Google Agent Development Kit (`google-adk` 2.13.0): `LlmAgent`, `Runner`, `InMemorySessionService`, function tools with `ToolContext`, `before_model`, `after_model` and `before_tool` callbacks, and the `Gemini` model with HTTP retry options; plus the [context-orchestration-engine](../../tools/context-orchestration-engine/) tool from this repository for shared memory.
- **Models**: Gemini via `GOOGLE_API_KEY` (default `gemini-3.8-flash` for every agent, overridable per agent); an offline mock model for keyless runs and tests.
- **External APIs / Tools**: Google Gemini API (live mode only); `git` (clone and diff only); SQLite (standard library).

---

## Architecture & Data Flow

```
 team> clone https://github.com/o/r and fix: <bug>
          |
          v
 guardrails: request + repo source --> create task --> git clone --depth 1 into workspace/<task_id>/
          |
     +----+-----------------------------------------------------------+
     |   SHARED MEMORY  (shared_memory/ + context-orchestration-engine)
     |   decisions, artifacts, issues, failed attempts, notes in SQLite
     |   written ONLY by the reconciler
     |
     |   Architect -> Junior -> Senior -> Junior -> Senior
     |
     |   1. Context Compiler: shared memory --> briefing (token budget)
     |   2. ADKGateway: NEW ADK session, include_contents="none"
     |      +-----------------+  +-----------------+  +------------------+
     |      | architect_agent |  |    jnr_agent    |  |    snr_agent     |
     |      | list/read       |  | list/read/write |  | list/read/diff   |
     |      | root cause +    |  | fix + test      |  | review the diff  |
     |      | fix decisions   |  | (no decisions)  |  | (no artifacts)   |
     |      +-----------------+  +-----------------+  +------------------+
     |      ADK callbacks: injection block, secret redaction, role policy,
     |      write sandbox (no .git, allowlist, size and count caps)
     |   3. JSON claims --> State Reconciler --> shared memory
     |      (provenance stamped by the engine; "fixed" stays a claim)
     |   4. commit turn to SQLite --> next agent
     +----------------------------------------------------------------+
          |
          v
 workspace/<task_id>.patch   +   python main.py memory <task_id>
```

| Path | Role |
| :--- | :--- |
| `main.py` | The single entry point: interactive CLI and subcommands |
| `architect_agent/agent.py` | Architect persona, read tools, policy, `root_agent` |
| `jnr_agent/agent.py` | Junior persona, read/write tools, policy (no decisions, no unwritten files), `root_agent` |
| `snr_agent/agent.py` | Senior persona, read + `show_diff` tools, policy (no artifacts), `root_agent` |
| `shared_memory/engine.py` | Imports the context-orchestration-engine from `tools/` |
| `shared_memory/handoff.py` | The loop: engine orchestrator + `ADKGateway` (one fresh ADK session per turn) |
| `shared_memory/protocol.py` | Roles, the build and fix pipelines, default model, Gemini retry settings |
| `shared_memory/guardrails.py` | Shared guardrail checks and the ADK callback factory |
| `shared_memory/workspace.py` | Clone, diff and patch, plus the `list_files`, `read_file`, `write_file` and `show_diff` ADK tools |
| `mock_llm.py` | Offline ADK `BaseLlm` with scripted replies |

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.11+
- pip
- `git` on your PATH (for clone and fix)
- A full clone of this repository: the team imports `tools/context-orchestration-engine/` (or set `COE_TOOL_PATH`)
- For live runs only: a Gemini API key from Google AI Studio. Everything also runs offline with no key.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/engineering-team
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
   Always run inside this venv. If you see `Missing dependency: google.genai`, the venv is not active, and `main.py` prints the exact commands to fix it.

3. **Configure Environment Variables (live runs only):**
   ```bash
   cp .env.example .env      # then uncomment GOOGLE_API_KEY and set it
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | Only for live runs | *None* | Gemini API key. When unset, runs use the offline mock model. |
| `ARCHITECT_MODEL` | No | `gemini-3.8-flash` | Model for the Architect |
| `JUNIOR_MODEL` | No | `gemini-3.8-flash` | Model for the Junior Engineer |
| `SENIOR_MODEL` | No | `gemini-3.8-flash` | Model for the Senior Engineer |
| `TEAM_WORKSPACE` | No | `workspace` | Where clones, written files and patches go (one subfolder per task) |
| `COE_TOOL_PATH` | No | `../../tools/context-orchestration-engine` | Location of the context-orchestration-engine |

Options for every command: `--mock`, `--real`, `--db PATH` (default `team.db`), `--budget N` (default 1200), `--stop-after N`, `--show-context`. Task IDs may be shortened to any unambiguous prefix.

---

## How to Run

```bash
python main.py
```
opens the interactive CLI:
```
team> clone https://github.com/owner/repo and fix: crash when the list is empty
team> clone "C:\My Repos\app" and fix: dates are off by one     (quote local paths with spaces)
team> build a small URL shortener with tests
team> tasks
team> memory <task_id>      shared memory: decisions, artifacts, issues, who wrote what
team> diff <task_id>        the fix as a patch
team> files <task_id>       the files in the task workspace
team> resume <task_id>      continue a stopped or failed run
team> quit
```

The same without the prompt:
```bash
python main.py fix https://github.com/owner/repo "crash when the list is empty"
python main.py ask "clone https://github.com/owner/repo and fix: crash when the list is empty"
python main.py build "a CLI to-do manager with tests"
python main.py memory <task_id>
python main.py diff <task_id>
python main.py resume <task_id>
```

Without `GOOGLE_API_KEY`, everything runs on the offline mock. With it, live Gemini is used (or force either with `--mock` / `--real`). Outputs: the clone and changed files in `workspace/<task_id>/`, the fix in `workspace/<task_id>.patch`, and shared memory in `team.db`.

Each agent is also a standard ADK agent folder: ADK's agent loader discovers `architect_agent`, `jnr_agent` and `snr_agent` here (verified). Running one alone with `adk web` bypasses the shared-memory handoff and was not tested.

---

## Example Input & Output

### Example Input
```
python main.py build
```
This runs the built-in request offline: "Build a small Python command-line to-do manager that stores tasks in a JSON file, with add, list and done commands."

### Example Output
Real output from the offline mock run (Windows 11, Python 3.12.2, google-adk 2.13.0). The model text is scripted, but ADK sessions, callbacks, function tools, file writes, the guardrails and the engine all run for real.
```
turn 2/5  junior  (mock)
  task       Junior engineer: implement the recorded design as source files with write_file, following every recorded decision.
  briefing   303 of 1200 tokens, omitted: none
  reconciled +0 decisions, +2 artifacts, 0 versioned, +1 issues, 0 fix claims kept open
  guardrail  decision-to-issue: Switch storage to SQLite
...
task-224cee59  completed  (5/5 steps)
  agents used                 architect, junior, senior
  raw conversation transfers  0
  peak briefing tokens        516
  files in workspace          tests/test_store.py, todo/cli.py, todo/store.py
  open issues                 4
    I-1 [medium] Junior proposed a design change (needs Architect sign-off): Switch storage to SQLite
    I-2 [high] done command accepts unknown task ids and reports success (fix claimed by senior, unverified)
    I-3 [medium] no automated tests for the store (fix claimed by senior, unverified)
    I-4 [low] tasks.json is written without a lock; concurrent runs can lose updates
```
`python main.py memory task-224cee59` (excerpt):
```
decisions (3)
  - Use argparse subcommands add, list and done  (reason: Standard library only; matches the three requested commands; by architect, turn 1)
artifacts (4)
  - todo/store.py v2  (by junior, then junior; unverified)
issues (4)
  - I-2 [high] open: done command accepts unknown task ids and reports success  (opened by senior; fix claimed by senior)
history (5)
  - turn 3 senior: Reviewed store and CLI against the design.
```
The mock-written files are real: their own tests give `2 passed`. In fix mode, the offline mock only demonstrates the flow (clone, tools, diff, patch). It writes a `FIX_NOTES.md` saying no real fix was made and opens an issue saying so. Real fixes need `GOOGLE_API_KEY`.

### Live Gemini runs (real key, `gemini-2.5-flash` then `gemini-3.8-flash`, free tier)
- **Run 1 (build):** 4 of 5 turns before the free-tier limit (5 requests per minute per model) stopped it. The live Junior *claimed* it wrote `persistence.py` twice without ever calling `write_file`. The live Senior called `list_files`, found nothing, and opened a high-severity issue. The engine kept the Junior's "fixed" claim open. That run led to the tool-first instruction, the Junior's unwritten-file guardrail, the Gemini retry settings and the clean resumable error.
- **Run 2 (build, after those fixes):** the Junior actually wrote `todo.py` and `test_todo.py`, and the generated tests pass (`10 passed`). The Senior listed reviewed files as its own artifacts, which led to the Senior's no-artifacts guardrail. The run reached 3 of 5 turns in 25 minutes, because free-tier retries waited 6 to 12 minutes per turn.
- **Clone and fix:** a live run against a small repository with two real bugs (`word_count` over-counting on double spaces, `average_word_length` dividing by zero on empty text) was started. The clone succeeded, but the Architect's first turn had not finished when this was committed, because it was waiting out free-tier quota. **Live fix mode is therefore not verified yet**. Only its offline flow (clone, tools, diff, patch) is tested.

---

## How to Test

```bash
pip install -r requirements.txt
python -m pytest            # 63 tests, all offline: no key, no network (git needed for the fix tests)
python -m pyflakes architect_agent jnr_agent snr_agent shared_memory tests main.py mock_llm.py
```

What the suite checks, beyond unit coverage:
- **Handoffs**:
  - each agent turn's first model request holds exactly one user message, equal to the briefing stored in shared memory;
  - no request ever contains another agent's reply;
  - 0 raw transfers.
- **Separation**: three ADK packages that never import each other, each with its own tools and `include_contents="none"`.
- **Clone and fix** (against a local git repo with a real bug):
  - unsafe sources are refused (`ssh`, `git@`, `ext::`, `file://`, `http://`, option-like strings);
  - `.git` is hidden and unwritable;
  - `show_diff` and the patch include modified and new files;
  - `fix` and `ask` run end to end.
- **Guardrails**: request refusal, injection blocking (the model is never called), secret redaction, role policies (including the two found live), and the write sandbox.
- **CLI**: natural-language parsing (URLs, quoted local paths), the interactive prompt, options before and after the subcommand, stop and resume, `memory`, `files` and `diff`.
- **Outcome**: the code the team writes passes its own tests, and a failed model call gives a clean, resumable error.

---

## Known Limitations

- **Free-tier Gemini is slow.** With 5 requests per minute per model, and several requests per turn once tools are involved, a five-turn run can take 30 minutes or more while retries wait. A paid key or `*_MODEL` overrides spreading agents across models helps. If retries run out, the run stops cleanly and `resume` continues it.
- **The offline mock cannot fix real bugs.** It demonstrates the flow only and says so in its output.
- **Fixes are never executed or verified.** The cloned repository's tests are not run (by design: no untrusted code runs on your machine). Issues are never closed automatically, and even the Senior's "verified" stays a recorded claim. Run the tests yourself and apply the `.patch` after reviewing it.
- **Strictly sequential, fixed pipeline**: Architect, Junior, Senior, Junior, Senior. There is no loop until the review is clean.
- **Large repositories:** `list_files` returns at most 400 paths per call (agents can list a sub-folder), `read_file` returns up to 20,000 characters, and the agents may write up to 40 files per task. Tool results are not counted in the briefing token budget.
- **Not self-contained**: imports `tools/context-orchestration-engine/` from this repository (or `COE_TOOL_PATH`).
- **Fail-closed injection guard**: injection-like text in shared memory blocks every later turn that sees it, by design. The regex catches common phrasings, not every attack.
- **Tested on** Windows 11, Python 3.12.2, google-adk 2.13.0, git 2.x. Python 3.11 and Linux/macOS have not been run.

---

## Security & Privacy Considerations

- **Secrets Handling**: `GOOGLE_API_KEY` comes from the environment (a local `.env` loaded by python-dotenv; `.env` is gitignored). It is never written to SQLite, the workspace or patches. Requests containing secret-like strings are refused, secrets in replies are redacted, and file writes containing secrets are refused.
- **Data Privacy**: in live mode, each agent turn sends Google's Gemini API the agent's persona and output contract, the compiled briefing (the request plus excerpts of shared memory) and the contents of repository files and diffs that agent reads. Do not point it at a repository you may not share with Google. Nothing leaves the machine in mock mode except the `git clone` itself. Run data stays local: `team.db`, `workspace/<task_id>/` and `workspace/<task_id>.patch`, all gitignored. There is no telemetry.
- **Safety**:
  - Agents never execute code. The only processes started are `git clone --depth 1` (HTTPS or a local folder only, with `GIT_TERMINAL_PROMPT=0`) and read-only `git diff`/`status` plus `git add --intent-to-add` inside the clone.
  - Only the Junior can write files: relative paths inside its task folder, never `.git`, an extension allowlist of source, config and doc types, 100 KB per file, 40 files per task.
  - These limits are enforced in both the ADK `before_tool_callback` and the tool itself.
  - Review the patch before applying it.

---

## Future Improvements

- [ ] Opt-in, sandboxed (container) test runs so a fix can be verified and its issue closed on evidence.
- [ ] Loop Junior and Senior until the review is clean, with a turn cap.
- [ ] Open a pull request from the patch (opt-in, with confirmation).
- [ ] Optional ADK `LiteLlm` models for non-Gemini providers.

---

## License

MIT. See [`LICENSE`](LICENSE) (Copyright (c) 2026 Vivan Rajath), compatible with the repository's MIT license.
