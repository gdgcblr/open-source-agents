# Murphy

> **Anything that can go wrong, will. Test it first.**
> Murphy stress-tests any tool-using AI agent against simulated users and broken tools, enforces tool-call policies, verifies outcomes against ground truth, and shows exactly what happened in one HTML report.

## Quickstart (2 minutes, no model, no API key)

```bash
cd agents/agent-stress-lab
python3.12 -m venv .venv && source .venv/bin/activate     # Python 3.12, not 3.13+
pip install -r requirements.txt && pip install -e .        # installs the `murphy` command
murphy run -c tests/fixtures/scripted.yaml                 # offline demo: ~5s, ends in "CI FAIL ... dup"
murphy ui                                                  # opens the HTML report
pytest -q                                                  # 86 offline tests
```

That run uses a scripted agent and user, so it needs no model. To test a real LLM agent, see [Prerequisites](#prerequisites) (Ollama + Gemma) and [How to Run](#how-to-run).

**Key terms:** a *persona* is a simulated customer (goal + hidden facts). A *fault scenario* is what breaks (for example "first `book_pickup` times out after committing"). A *run* is one persona × one fault, and a *matrix* is all of them. A *check* decides pass/fail from real state, and a *label* (`dup`, `wrong`, …) says why a run failed.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Agents are tested on the happy path, with clean prompts and tools that always succeed. Production is different. Users give half the information, change their minds and give up. Tools time out, return 500s, answer slowly or return malformed data. Agents then retry side-effecting calls and do things twice (two pickups, two refunds), and nobody can reproduce what went wrong.
- **Intended Users**: Developers and teams shipping tool-using agents (support bots, booking/ops agents, internal copilots) who want a repeatable pre-release and CI gate, framework-agnostic and local-first.

### Key Features
- **Simulated users**: an LLM role-plays personas with hidden facts, reveal rules, patience and a give-up signal. Local Gemma via Ollama by default; no API key needed.
- **Or be the user yourself**: `murphy chat` lets you type the customer's side live, seeing every tool call, fault and policy hit as it happens. The run is judged, reported and replayable like any other.
- **Chaos proxy for MCP tools**: sits in front of *your* MCP server(s) and injects `timeout_after_commit`, `error_500`, `slow` and `malformed` faults by tool glob, call index or seeded rate.
- **Policy guardrails**: declarative `idempotent`, `requires_before`, `max_calls` and `budget` rules, in `monitor` (record) or `enforce` (block) mode. They are evaluated on ground truth, so a retry after a committed timeout is still caught.
- **Ground-truth checks**: generic trace rules plus Python or HTTP state checks. The verdict comes from what actually happened, not from an LLM's opinion.
- **Flight recorder + replay**: every user turn, agent reply and tool call goes on one timeline (`trace.jsonl`). Replay a failure with the same user turns, faults and seed against a fixed agent or an enforced policy.
- **Reports for people and CI**: a self-contained `report.html` (heatmap → run timeline → replay diff), plus `results.json`, `junit.xml`, `report.md`, and an exit code driven by thresholds.
- **Plug and play**: one `murphy.yaml`; targets, users and checks are built-ins or `module:attr` import paths.

### Bundled examples

| Example | Agent under test | Tools | What it catches |
| :--- | :--- | :--- | :--- |
| [`examples/shop_returns`](examples/shop_returns/murphy.yaml) | Google ADK returns agent (`naive` / `fixed`) | Mock shop MCP server | Duplicate pickups after a committed timeout; booking ineligible items |
| [`examples/payments_refunds`](examples/payments_refunds/murphy.yaml) | Google ADK billing agent (`naive` / `fixed`) | Mock payments MCP server | Double refunds (`dup`), refunds without a policy check (`unsafe`), wrong amounts (`wrong`) |
| [`examples/http_support_bot`](examples/http_support_bot/murphy.yaml) | Plain HTTP service, no framework (`/chat`, `?mode=fixed`) | None (no MCP) | Duplicate support tickets when the customer repeats themselves, verified through the bot's admin API |

Each example runs offline in the test suite with scripted agents (`tests/test_examples.py`), and live with local models.

### The report

`report.html` is a single self-contained file (no network, works as a CI artifact) with:
- **Overview**: a one-line verdict, completion, failures by label, policy violations/blocks, cost per successful task, and the CI gate status.
- **Personas × faults matrix**: every cell is one conversation. Rows show each persona's goal, columns show what was injected.
- **Run detail**: what went wrong (failed checks plus how to fix), the full conversation and tool calls on one timeline (⚡ injected fault, ⚠ policy violation, ⛔ blocked call, DUPLICATE side effect; results expandable), the checks table, a before/after replay comparison, and copyable replay commands.
- **How to read this report**: built-in examples of every failure label, fault type and policy mode.

---

## Technical Stack

- **Language & Runtime**: Python 3.11–3.12
- **Agent Framework / Core Library**: Model Context Protocol (FastMCP 4 proxy), Google ADK adapter (optional extra), LiteLLM for the simulated user
- **Models**: Gemma 4 E4B via Ollama (default, local) for both the simulated user and the demo agent; any LiteLLM model works (for example Gemini) through config
- **External APIs / Tools**: none required. The example uses a bundled mock shop MCP server.

---

## Architecture & Data Flow

```
                 ┌──────────────────────── murphy.yaml ────────────────────────┐
                 ▼                                                                │
┌──────────┐  ┌─────────────────────────────────────────────┐  ┌──────────────┐  │
│  users/  │  │                    core/                    │  │  targets/    │  │
│ llm      │─▶│ orchestrator · trace · verdict · ci         │─▶│ adk · http   │  │
│ scripted │  │   (framework-agnostic; test-enforced)       │  │ scripted     │  │
│ replay   │  └───────┬─────────────────────┬───────────────┘  └──────┬───────┘  │
└──────────┘          │                     │                         │ MCP stdio │
              ┌───────▼───────┐     ┌───────▼───────┐         ┌───────▼───────┐ │
              │   checks/     │     │   report/     │         │    proxy/     │◀┘
              │ trace · python│     │ html · json   │         │ faults·policy │──▶ your MCP
              │ http          │     │ junit · md    │         │ recorder      │    server(s)
              └───────────────┘     └───────────────┘         └───────────────┘
```

Per run, the orchestrator writes `<run>/proxy.json` (upstreams, faults, policy, seed) and starts the target. The target spawns the proxy (`python -m murphy.proxy <run>`), and the proxy spawns your MCP servers. The simulated user and the agent talk; every tool call passes through faults → policy → upstream → recorder. Afterwards the timelines are merged into `trace.jsonl`, checks run, and `result.json` is written.

**Separation of concerns:** `core`, `config`, `checks` and `report` never import ADK, FastMCP, LiteLLM or the examples (`tests/test_architecture.py` enforces this). The shop demo in `examples/shop_returns/` uses only the public config, like any other user would. The coordinator is hub-and-spoke (the orchestrator is the only hub), so coordination cost grows O(n) with components, not O(n²) as in an agent mesh.

---

## Prerequisites

- **Python 3.12** (recommended and tested; 3.11 also works). Python 3.13+ is not supported yet, and `pip install` will refuse it. On macOS: `brew install python@3.12`, then use `python3.12` explicitly, because `python3` may point to a newer version.
- [Ollama](https://ollama.com) for local models: `brew install ollama`, then `ollama serve`
- A tool-calling local model: `ollama pull gemma4:e4b` (about 9.5 GB on disk; `qwen3:4b` is a smaller alternative)
- No API keys for the default setup

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/agent-stress-lab
   ```

2. **Create a virtual environment and install:**
   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   pip install -r requirements.txt    # pinned, tested versions
   pip install -e .                   # installs the `murphy` command
   ```

   Every new terminal needs `source .venv/bin/activate` again (or call `.venv/bin/murphy` directly). Run all commands from `agents/agent-stress-lab`; paths like `runs/…` and `examples/…` are relative to it.

3. **Configure environment variables (optional):**
   ```bash
   cp .env.example .env
   ```

4. **Verify models and tool calling:**
   ```bash
   murphy check -c examples/shop_returns/murphy.yaml
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `SIM_MODEL` | No | `ollama_chat/gemma4:e4b` | LiteLLM model id for the simulated user |
| `TARGET_MODEL` | No | `ollama_chat/gemma4:e4b` | Model for the example ADK agent (must support tool calling) |
| `OLLAMA_API_BASE` | No | `http://localhost:11434` | Ollama endpoint |
| `GEMINI_API_KEY` | No | *None* | Only if you switch a model to Gemini |
| `PRICE_PER_1K_TOKENS` | No | *None* | Enables cost-per-successful-task in reports |
| `MURPHY_CONFIG` | No | `./murphy.yaml` | Default config path |
| `FASTMCP_LOG_LEVEL` | No | `WARNING` | Log level for proxy and upstream subprocesses |

### `murphy.yaml` in one screen

```yaml
version: 1
name: my-agent
python_path: ["."]                          # where your agent/check modules live

target: {type: adk, factory: "my_agent:build", model: "${TARGET_MODEL:-ollama_chat/gemma4:e4b}"}
# target: {type: http, url: http://localhost:8000/chat}     # POST {session_id, message} -> {reply}

tools:                                      # your MCP server(s); Murphy fronts them
  - {name: orders, command: [python, -m, my_mcp_server], env: {}, cwd: .}   # inherits your env; inherit_env: false to isolate

user: {type: llm, model: "${SIM_MODEL:-ollama_chat/gemma4:e4b}"}
personas: [{file: personas/*.yaml}]

faults:                                     # matrix columns
  - {id: no-fault}
  - {id: timeout, inject: [{tool: book_pickup, type: timeout_after_commit, on_call: 1}]}
  - {id: flaky, inject: [{tool: "get_*", type: error_500, rate: 0.3}]}

policy:
  mode: monitor                             # off | monitor | enforce
  rules:
    - {id: no-double-booking, type: idempotent, tool: book_pickup, key: [order_id, item_sku]}
    - {id: eligibility-first, type: requires_before, tool: book_pickup, prior: check_return_eligibility,
       match: [order_id, item_sku], prior_result: {eligible: true}}
    - {id: budget, type: budget, max_tool_calls: 20}

checks:                                     # all must pass
  - {id: single-booking, type: trace, rule: max_calls_per_key, tool: book_pickup, key: [order_id, item_sku], max: 1, label: dup}
  - {id: outcome, type: python, fn: "my_checks:order_ok", label: wrong}
  - {id: api-state, type: http, url: "http://localhost:8000/admin/pickups?order=${vars.order_id}", path: count, equals: 1}

ci: {fail_if: {completion_below: 0.8, any_label: [dup]}}
```

`${VAR}` and `${VAR:-default}` come from the environment (and a `.env` beside the config). They are substituted into string values after YAML parsing, so an env value can never change the config's structure. `${vars.x}` in checks comes from each persona's `vars`. `python` in a tool command resolves to the running interpreter. The full schema is in `murphy/config/schema.py`.

### Plugging in your own pieces

```python
# Custom target: any agent, any framework
class MyTarget:
    label = "my-agent"
    async def start(self, tools): ...          # tools: ToolEndpoint (proxy command) or None
    async def send(self, message): ...         # -> murphy.targets.base.TargetReply(text, tokens)
    async def close(self): ...
# murphy.yaml:  target: {type: "my_pkg.stress:MyTarget", some_option: 1}

# Custom check: anything you can compute from the run
def refund_issued(ctx):                       # ctx: RunContext(run_dir, persona, vars, trace, end_reason)
    return my_db.refunds(order=ctx.vars["order_id"]) == 1
# murphy.yaml:  checks: [{id: refund, type: python, fn: "my_checks:refund_issued", label: wrong}]
```

---

## How to Run

| Command | What it does |
| :--- | :--- |
| `murphy init [dir]` | Scaffold `murphy.yaml`, an example persona and `.env.example` |
| `murphy validate -c FILE` | Load and validate a config |
| `murphy check -c FILE` | Check Ollama, models and the target model's tool calling |
| `murphy run -c FILE [--personas a,b] [--faults x,y] [--policy MODE] [--target REF]` | Run the persona × fault matrix; exit 1 if `ci.fail_if` trips |
| `murphy chat -c FILE [--persona p] [--fault f]` | You type the user's messages; Murphy still injects faults and judges |
| `murphy replay RUN_DIR [--target REF] [--policy MODE]` | Re-run a recorded conversation against a fix |
| `murphy report MATRIX_DIR` | Re-render all reports |
| `murphy ui [MATRIX_DIR]` | Open `report.html` (default `runs/latest`) |

```bash
murphy init my-project                    # scaffold murphy.yaml + persona + .env.example
murphy validate -c my-project/murphy.yaml

# The bundled example (ADK returns agent + mock shop MCP server):
murphy run -c examples/shop_returns/murphy.yaml --personas cooperative,forgot-order-id --faults no-fault,timeout
murphy ui                                 # opens runs/latest/report.html

# Other examples:
murphy run -c examples/payments_refunds/murphy.yaml --personas full-refund --faults no-fault,refund-timeout
python examples/http_support_bot/server.py &                # start the HTTP agent first
murphy run -c examples/http_support_bot/murphy.yaml
murphy run -c examples/http_support_bot/murphy.yaml --target "http://127.0.0.1:8010/chat?mode=fixed"

# Be the user yourself (Murphy still breaks tools, enforces policies and judges the run):
murphy chat -c examples/shop_returns/murphy.yaml --persona cooperative --fault timeout

# Prove a fix on the exact failing conversation:
murphy replay runs/latest/cooperative__timeout --target shop_returns.agent:fixed
murphy replay runs/latest/cooperative__timeout --policy enforce   # default target: the recorded one

# CI gate (exit 1 when ci.fail_if trips; JUnit at runs/latest/junit.xml):
murphy run -c murphy.yaml
```

---

## Example Input & Output

### Example Input
```bash
murphy run -c examples/shop_returns/murphy.yaml --personas cooperative,forgot-order-id --faults no-fault,timeout
```

### Example Output
Real output from a live run: Gemma 4 E4B on Ollama for both the simulated user and the naive ADK agent, on a MacBook (Apple Silicon).

```
murphy 0.2.0 · shop-returns · 2 personas × 2 faults · target shop_returns.agent:naive · policy monitor
  cooperative          no-fault       PASS             2 turns · 3 tools · 36.5s
  cooperative          timeout        FAIL dup         5 turns · 4 tools · 76.4s
  forgot-order-id      no-fault       PASS             7 turns · 4 tools · 108.0s
  forgot-order-id      timeout        FAIL dup         8 turns · 6 tools · 92.2s

                 no-fault    timeout
cooperative      PASS        FAIL dup
forgot-order-id  PASS        FAIL dup

completion        2/4 (50%)
failure labels    dup=2
avg user turns    5.5
faults fired      2
policy            2 violations, 0 blocked
agent tokens      50248 (25124/success)
report: runs/<matrix>/report.html
CI FAIL: completion 50% < 60%
CI FAIL: 2 run(s) labelled 'dup'
```

The failing run's timeline (from `report.md`; `report.html` shows the same as a two-column chat + tool-call view). The agent was told the booking timed out, but it had committed, so the retry booked a second pickup and the agent told the user it succeeded:

```
 t1  USER   Hello, I need to start a return for an item. My order ID is A12.
      AGENT  The user wants to start a return and has provided the Order ID "A12". The next step is to…
 t2  USER   Yes, A12 is correct. I would like to return the running sneakers, size 9, as they are too…
      TOOL   → get_order(order_id=A12)  ✓ {"order_id":"A12","delivered_on":"2026-10-17","items":[{"sk…
      TOOL   → check_return_eligibility(item_sku=SNK-42, order_id=A12)  ✓ {"eligible":true,"reason":"delivered 7 days ago, within win…
      AGENT  The running sneakers are eligible for return. I can book a pickup for you. Would you like…
 t3  USER   Yes, please schedule the pickup. What is the next step?
      TOOL   → book_pickup(item_sku=SNK-42, order_id=A12, reason=too small)  ⚡ TIMEOUT (injected, but committed)
      AGENT  I apologize, I encountered a temporary system error while scheduling the pickup. Would yo…
 t4  USER   Yes, please try booking it again. Thank you.
      TOOL   → book_pickup(item_sku=SNK-42, order_id=A12, reason=too small)  ✓ {"pickup_id":"PU-2","status":"scheduled","window":"tomorrow…  ⚠ policy: no-double-booking
      AGENT  I have successfully scheduled your return pickup! Your pickup ID is PU-2, and the window …
 t5  USER   Thank you so much. That is very helpful.  [goal_met]

 check    single-booking: book_pickup executed {'A12/SNK-42': 2} times per key (max 1)
 hint     A side-effecting tool ran twice. Check get_pickup_status before retrying, or enforce no-double-booking.
```

Two ways to fix it, each proven by a live replay of the same conversation:

```
$ murphy replay runs/<matrix>/cooperative__timeout --target shop_returns.agent:fixed
 before  [shop_returns.agent:naive, policy=monitor]  FAIL [dup]
         tools: get_order → check_return_eligibility → book_pickup⚡ → book_pickup
 after   [shop_returns.agent:fixed, policy=monitor]  PASS
         tools: get_order → check_return_eligibility → book_pickup⚡ → get_pickup_status

$ murphy replay runs/<matrix>/cooperative__timeout --policy enforce
 before  [shop_returns.agent:naive, policy=monitor]  FAIL [dup]
         tools: get_order → check_return_eligibility → book_pickup⚡ → book_pickup
 after   [shop_returns.agent:naive, policy=enforce]  PASS
         tools: get_order → check_return_eligibility → book_pickup⚡ → book_pickup⛔ → book_pickup⛔
```

Observed while testing: Gemma 4 E4B sometimes leaks its planning text into replies (visible in t1 above). This is a real finding about the agent under test, which the report makes visible.

---

## How to Test

```bash
pytest -q          # 86 offline tests: no model, no network, no API keys
```

The suite covers:
- the config loader (env interpolation, readable errors), fault engine, policy engine and checks
- the proxy over a real MCP upstream: every fault type, both policy modes, state persistence, multiple namespaced upstreams
- the orchestrator and replay with a scripted agent and user
- all four report formats, including an XSS-escape test for the HTML report
- the CLI end to end (`init → validate → run → replay → ui`, CI exit codes)
- an architecture test that keeps the core free of framework imports

`tests/fixtures/scripted.yaml` shows how to run Murphy in CI without any model.

---

## Project Layout

```
agents/agent-stress-lab/
├── murphy/                  # the package (CLI: murphy/cli.py)
│   ├── config/              # murphy.yaml schema + loader
│   ├── core/                # orchestrator, trace, verdict, CI gate (framework-agnostic)
│   ├── proxy/               # MCP proxy: faults, policies, recording
│   ├── checks/              # trace / python / http checks
│   ├── targets/             # agent adapters: adk, http, scripted
│   ├── users/               # simulated users: llm, scripted, human (chat), replay
│   └── report/              # html (template.html), json, junit, markdown
├── examples/                # shop_returns · payments_refunds · http_support_bot
├── tests/                   # 86 offline tests; fixtures/scripted.yaml = no-model config
└── runs/                    # run output (gitignored); runs/latest → newest matrix
```

**Where to change what:** a new fault type goes in `proxy/faults.py` + `proxy/server.py`; a new policy rule in `config/schema.py` + `proxy/policy.py`; a new check in `checks/builtin.py`; a new agent framework as a class in `targets/`; report UI in `report/template.html`. Keep `core`, `config`, `checks` and `report` free of ADK/FastMCP/LiteLLM imports (`tests/test_architecture.py`). Run `pytest -q` before every commit.

---

## Troubleshooting

| Symptom | Fix |
| :--- | :--- |
| `requires a different Python: 3.15.0 not in '<3.14,>=3.11'` | Create the venv with `python3.12 -m venv .venv` |
| `zsh: command not found: murphy` | Activate the venv (`source .venv/bin/activate`) or use `.venv/bin/murphy` |
| `no such file or directory` / `does not exist` for `runs/…` | `cd` into `agents/agent-stress-lab` first; paths are relative to it |
| `murphy check` says ollama not reachable | Start it: `ollama serve` (or the Ollama app) |
| `model … not found` / `✗ user.model` | `ollama pull gemma4:e4b` |
| `✗ tool calling with …` | Pick a tool-capable model: `TARGET_MODEL=ollama_chat/qwen3:4b` in `.env` |
| `structured output is unavailable` | Already handled: the simulated user does not use JSON mode. Upgrade if you see it |
| HTTP example: `Connection refused` | Start the bot first: `python examples/http_support_bot/server.py` |
| `zsh: no matches found: runs/…/*__replay-*` | No replays exist yet. To delete them safely use `find runs/<matrix> -maxdepth 1 -name '*__replay-*' -exec rm -rf {} +` |
| Replay: `recorded target … can't be loaded` | The agent module was renamed; pass `--target module:factory` |
| Live runs are slow | Expected on a laptop (30–120 s per run). Narrow with `--personas` / `--faults` |

---

## Known Limitations

- **LLM nondeterminism**: live runs vary between executions. Seeds are passed to the simulator, but local models are not bit-reproducible. Replay freezes the user turns and the faults; the agent's model still runs live (divergence is flagged).
- **Tool interception requires MCP**: agents whose tools are not MCP servers are judged on conversation plus state checks only. The `http` target does not see tool calls unless the service routes its MCP client through the proxy.
- **stdio upstreams only** in v0.2 (no HTTP/SSE MCP upstreams yet). Runs are sequential.
- **Policies cover tool calls only**: there is no input/output text guardrail (for example prompt-injection or PII detection in agent replies) yet.
- **Speed**: with Gemma 4 E4B on a laptop, each run takes from tens of seconds to a few minutes; use `--personas/--faults` to keep matrices small.
- Tested on macOS (Apple Silicon) with Python 3.12; Linux expected to work; Windows untested.

---

## Security & Privacy Considerations

- **Secrets Handling**: config values come from the environment or `.env` (gitignored); `.env.example` has placeholders only. MCP servers inherit your environment by default (`inherit_env: false` isolates them). Checks judge the real tool arguments. Everything persisted (`trace.jsonl`, `tools.jsonl`, `conversation.jsonl`, reports) masks values whose keys look secret (`*key*`, `*token*`, `*secret*`, `authorization`, …) and vendor-shaped secrets (`sk-…`, `AIza…`, `ghp_…`, `xox?-…`) as `***`. During a run, the raw tool log exists in the run directory until the run finishes.
- **Data Privacy**: local-first. With the default Ollama models no prompt leaves the machine. If you configure a hosted model, prompts and tool results go to that provider. Run artifacts stay in `runs/` (gitignored).
- **Safety**: `murphy.yaml` is trusted local input (it starts the commands you list); never point Murphy at a config you did not write. No `shell=True` anywhere. The HTML report embeds data as escaped JSON and builds the DOM with `textContent` (XSS-tested). The bundled backend is fully mocked.

---

## Future Improvements

- [ ] HTTP/SSE MCP upstreams and a network proxy mode for agents running as services
- [ ] LangGraph, OpenAI Agents SDK and A2A target adapters; entry-point plugin discovery
- [ ] Text guardrails (prompt-injection and PII checks on agent replies) and an optional LLM-rubric check
- [ ] Auto-generated personas from the agent's tool list
- [ ] Parallel runs, live-streaming UI, trend view across runs, OpenTelemetry export

---

## License

*This project is contributed under the repository's open-source license (MIT).*
