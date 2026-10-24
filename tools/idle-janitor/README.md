# idle-janitor

> Your AI assistant can spin up a container. **idle-janitor** is how it finally learns to clean up after itself — with ₹, Wh, and CO₂ receipts.

A **sustainable-dev-ops MCP server + CLI + live TUI** that audits forgotten Docker containers and local dev-server processes, estimates what they've cost you in rupees, watt-hours, and grams of CO₂, and gives your AI assistant policy-aware tools to reap them safely.

```
                                 idle-janitor
    ┌────────────────────────────────────────────────────────────────┐
    │ ₹47 • 18 Wh • 13 g CO₂ wasted on 3 idle resources today        │
    │ — ~2 phone charges, or one filter coffee                       │
    └────────────────────────────────────────────────────────────────┘
```

---

## Who this is for

### Primary users

| Who | What they feel | What they get |
|---|---|---|
| **Solo developers & students** on a laptop | Fan noise at 10 PM, laptop running hot, surprise ₹200 Firebase bill at month-end | A one-command snapshot of forgotten containers + dev servers, with ₹ / Wh / g CO₂ receipts. |
| **AI coding assistants** (Cursor, Claude Desktop, any MCP client) | They can spawn `docker run` and `yarn dev` for you \u2014 but have no symmetric way to clean up | A 9-tool MCP surface to audit, cost, policy-check, and (with the human's blessing) reap. |

### Beneficiary stakeholders (not users, but win when this exists)

- **Your wallet** \u2014 laptop electricity + cloud bills.
- **Your team** on shared free tiers (Supabase, Vercel, Firebase) \u2014 one person's forgotten resources steal everyone's quota.
- **The planet** \u2014 the `g CO\u2082` column isn't a cute flourish; it's a legitimate GreenOps signal, computed from the India CEA grid intensity (0.713 kg CO\u2082/kWh) or per-region factors for cloud resources.

### Future stakeholders (vision, not v1)

- **Startup FinOps leads** who want an org-wide "\u20b9X saved this week" dashboard.
- **Platform / SRE teams** baking this into developer-env templates.
- **Enterprises doing GreenOps / FinOps** across multi-cloud fleets.

### Explicitly NOT for

- **Sysadmins or production operators** \u2014 we deliberately refuse to touch system processes (launchd, WindowServer, your shell, your editor) and ship a `protect:` default clause for `postgres` / `name_contains: production`.
- **Enterprise multi-tenant compliance** \u2014 this isn't SOC-2; it's a laptop-first tool with cloud as a documented roadmap.

### Scope honesty

| Thing | v1 status |
|---|---|
| Local Docker containers | \u2705 Real \u2014 full Docker Engine API |
| Local dev-server processes | \u2705 Real \u2014 `psutil` + SIGTERM/SIGKILL |
| Local Firebase emulators (hub probe) | \u2705 Real \u2014 strictly `127.0.0.1:4400` |
| **AWS EC2** | \u26a0\ufe0f **Fixture-driven** \u2014 adapter architecture is real; data in the demo comes from `aws_fixture.example.yaml`; swap in `boto3.ec2.describe_instances()` to go live (see `janitor/aws_scan.py::_load_fixture`). We scoped out credential handling for v1 on purpose. |
| GCP / Vercel / Supabase | \u274c Roadmap only |

---

## Overview

### The problem

Developers routinely leave idle local containers, hot-reload dev servers, and tunnels running after a task is done. They silently drain laptop battery, hold RAM hostage, and (in the cloud) rack up charges that only surface at billing time. The usual fixes — `docker ps` roulette, reboots, cron killers — are either boring, destructive, or both.

More importantly, AI coding assistants (Cursor, Claude Desktop, Copilot) now **spawn** dev resources on your behalf. But there is no symmetric MCP surface to **reap** them. The agent that creates the mess should be able to clean it up — intelligently, with your consent, under policies you set, and with cost context you can feel.

### What idle-janitor gives you

Four surfaces, one shared data model:

| Surface | What it is | Who uses it |
|---|---|---|
| **MCP server** (`idle-janitor serve`) | 9 tools exposed to any MCP client | Your AI assistant (Cursor / Claude Desktop) |
| **CLI** (`idle-janitor status / history / reap / firebase / aws / ...`) | Human-first commands with rich output | You, in your terminal |
| **Live TUI** (`idle-janitor live`) | Refreshing dashboard with per-row policy decisions | Demos, standups, daily check-ins |
| **Autonomous watcher** (`idle-janitor agent --watch`) | Background loop that samples every N min and acts per policy | Set-and-forget cleanup |
| **Policy engine** (`~/.idle-janitor/policies.yaml`) | Declarative `protect` + `reap` rules in YAML | You configure once, everyone respects them |

### Key features

- **Audits Docker containers** — uptime, CPU%, memory, image, idle detection via docker-stats sampling.
- **Audits local dev-server processes** — `vite`, `next dev`, `uvicorn`, `nodemon`, `ngrok`, `ollama serve`, `cloudflared tunnel`, `firebase emulators:start`, and ~25 more. Matched with regex **word boundaries** + system-path/name blocklists so `SystemUIServer` and `launchd` are never surfaced or reaped.
- **Firebase emulator adapter** — probes the local Firebase emulator hub at `127.0.0.1:4400` (strictly loopback; nothing sent to Google) and surfaces running emulators with per-emulator cost estimates.
- **AWS adapter (fixture-driven in v1)** — reads an EC2 inventory from `aws_fixture.example.yaml` (or the file at `$AWS_FIXTURE_PATH`), computes real on-demand `$/hr`, Wh, ₹, and per-region g CO₂ per instance. Swap `_load_fixture()` for `boto3.ec2.describe_instances()` and the rest of the pipeline is live. See [Scope honesty](#scope-honesty) above.
- **Hero metric: ₹ + Wh + g CO₂** with a human analogy per output — *"₹47, 18 Wh, 13 g CO₂ wasted — ~2 phone charges."*
- **Local SQLite journal** (`~/.idle-janitor/history.db`) — enables `history_waste(window="7d")` and the TUI's weekly footer. No cloud, no network.
- **Policy engine** — declarative YAML. `protect` clauses are checked *inside* every terminate call, so no stale resource-id can be weaponized against your Postgres container.
- **Snooze** — tell the janitor to ignore a specific resource for N minutes.
- **Dry-run by default** everywhere. Reap is a two-call pattern: plan first, confirm, then execute.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: Model Context Protocol (MCP) Python SDK (`mcp>=2.3`, `MCPServer`)
- **Models**: None. The server is pure tooling; reasoning happens in whichever LLM your MCP client runs.
- **External APIs / Tools**:
  - **Docker Engine** via `docker` Python SDK (optional at runtime — falls back to process-only mode)
  - **OS process table** via `psutil`
  - **SQLite** (stdlib) for the local waste journal
  - **Rich + Typer** for the CLI and TUI
  - **PyYAML** for the policy file

---

## Architecture & Data Flow

```
                                 ┌─────────────────────────────┐
     ~/.idle-janitor/            │   policies.yaml (declarative│
     ├── policies.yaml  ───────► │   protect + reap rules)     │
     ├── history.db              └─────────────────────────────┘
     ├── snooze.json                           ▲
     └── demo_pids.json                        │
                                               │
   ┌──────────────────┐    ┌──────────────────┼──────────────────┐
   │  MCP Client      │    │                  │                  │
   │  (Cursor /       │    │           idle-janitor              │
   │   Claude)        │◄──►│                                     │
   └──────────────────┘    │  server.py  cli.py  tui.py          │
                           │        \     |     /                │
                           │         +----v----+                 │
                           │         |  scan   |  (shared core)  │
                           │         +----+----+                 │
                           │              |                      │
                           │   +----------+----------+           │
                           │   |                     |           │
                           │ docker_scan        process_scan     │
                           │   |                     |           │
                           │ cost.py  history.py  snooze.py      │
                           └──────────────────────────────────────┘
                                 |                 |
                           [Docker Engine]   [OS process table]
```

**Reap flow** (same for CLI, TUI auto-mode, and MCP agent):

1. **Scan** → unified list of resources (docker + processes) with uptime, CPU%, mem, Wh, ₹, g CO₂.
2. **Journal** → one SQLite row per resource per scan.
3. **Evaluate policies** → each resource gets a decision: `protect` / `reap` / `warn` / `none`.
4. **Dry-run plan** → shown to human or agent.
5. **Execute** → per-resource allowlist re-check inside `terminate`, then stop. Reap journaled to `reap_log` table.

---

## Prerequisites

- **Python 3.10+** (the `mcp` SDK requires it).
- **pip** (or `uv`).
- **Docker Desktop / Engine** — optional. The server degrades gracefully to "process-only" mode if Docker isn't running.
- An **MCP-compatible client** to talk to the server (Cursor or Claude Desktop) — optional, since the CLI and TUI are fully usable standalone.
- No API keys. No cloud credentials. No network calls.

---

## Installation & Setup

```bash
cd tools/idle-janitor

# 1. Virtual env
python3.12 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate

# 2. Install (editable so the `idle-janitor` command is on your PATH)
pip install --upgrade pip
pip install -e .

# 3. (Optional) Initialize the policy file
idle-janitor policies --init

# 4. Try it
idle-janitor --help
```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| *(none required)* | — | — | idle-janitor has no required env vars and makes no network calls. |
| `IDLE_CPU_THRESHOLD` | No | `1.0` | *(reserved for a future release)* CPU% below which a resource is treated as idle. |
| `INR_PER_KWH` | No | `8.0` | *(reserved)* Electricity tariff for the rupee estimate. |

The runtime policy and waste journal live under `~/.idle-janitor/` and never leave your machine.

---

## How to Run

### As a CLI (recommended for a first look)

```bash
idle-janitor status                     # one-shot snapshot with ₹/Wh/CO₂
idle-janitor live                       # refreshing dashboard, Ctrl+C to exit
idle-janitor history --window 7d        # waste over the last week
idle-janitor aws                        # list EC2-like instances (fixture-driven in v1)
idle-janitor firebase                   # list local Firebase emulators + est. cost
idle-janitor policies --init            # write ~/.idle-janitor/policies.yaml
idle-janitor policies --evaluate        # see what policies say about now
idle-janitor reap --dry-run             # plan a cleanup (default: dry-run)
idle-janitor reap --for-real            # actually stop them (per policy)
idle-janitor snooze proc:48213 60       # ignore this one for 60 min
idle-janitor agent --interval 300       # autonomous watcher, advisory by default
idle-janitor agent --autonomous --notify --max-reaps 5  # really reap, cap at 5 per run
idle-janitor serve                      # start the MCP server on stdio
```

### As an MCP server (for Cursor)

Open **Cursor Settings → MCP → Add new server** and paste:

```json
{
  "mcpServers": {
    "idle-janitor": {
      "command": "/absolute/path/to/tools/idle-janitor/.venv/bin/idle-janitor",
      "args": ["serve"]
    }
  }
}
```

Reload Cursor. You should see 9 tools under `idle-janitor`:
`list_idle_resources`, `estimate_waste`, `history_waste`, `list_aws_resources`, `list_firebase_emulators`, `safety_check`, `snooze_resource`, `terminate_resource`, `apply_policies`.

Then ask Cursor:

> *"Use idle-janitor to tell me what's idle on my machine and what it's cost me so far."*
> *"How much have I wasted this week?"*
> *"Apply my policies dry-run, show me what you'd kill."*

### As an MCP server (for Claude Desktop)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "idle-janitor": {
      "command": "/absolute/path/to/tools/idle-janitor/.venv/bin/idle-janitor",
      "args": ["serve"]
    }
  }
}
```

Restart Claude Desktop.

---

## MCP Tools

| Tool | What it does |
|---|---|
| `list_idle_resources(min_idle_minutes=0)` | Return every idle Docker container + dev-server process with uptime, CPU%, mem, ₹, Wh, g CO₂. Also records a snapshot to the local journal. |
| `estimate_waste(min_idle_minutes=0)` | Aggregate the above into a single headline string + per-resource list. |
| `history_waste(window="7d")` | Windowed waste summary from the SQLite journal. Supports `"7d"`, `"24h"`, `"60m"`, or raw seconds. |
| `list_aws_resources(include_stopped=False)` | List EC2-like instances with uptime, `$/hr`, cumulative `$`, `₹`, Wh, and per-region g CO₂. **v1 reads a YAML fixture, not live boto3** — see [Scope honesty](#scope-honesty). |
| `list_firebase_emulators()` | Probe the Firebase emulator hub (strictly `127.0.0.1:4400`) and list running emulators with per-emulator cost estimates. Degrades gracefully if the hub isn't running. |
| `safety_check(resource_id)` | Preview the guard verdict without side effects. Agents should call this before `terminate_resource` to explain to the user *why* a request would be refused. |
| `snooze_resource(resource_id, minutes=60)` | Mark a resource as "I'm using it, leave it alone" for N minutes. |
| `terminate_resource(resource_id, dry_run=True, force=False)` | Stop a Docker container or kill a dev-server process. `dry_run=True` by default. Allowlist re-checked inside `terminate`. |
| `apply_policies(dry_run=True, min_idle_minutes=0)` | Evaluate `~/.idle-janitor/policies.yaml` against the current snapshot. Returns every decision (`reap` / `warn` / `protect`) and, if `dry_run=False`, executes all `reap` decisions. |

---

## Policy Engine

Default policy file (`idle-janitor policies --init` writes this to `~/.idle-janitor/policies.yaml`):

```yaml
protect:                                 # ALWAYS win; never reaped, never recommended
  - image_contains: postgres
  - image_contains: mysql
  - image_contains: mariadb
  - name_contains: production
  - name_contains: prod-

rules:                                   # evaluated top-down; first match per resource
  - name: reap-stale-ngrok
    match: { kind: process, name_contains: ngrok, idle_minutes_min: 60 }
    action: reap
  - name: warn-stale-vite
    match: { kind: process, name_contains: vite, idle_minutes_min: 180 }
    action: warn
  - name: warn-very-old-containers
    match: { kind: docker, idle_minutes_min: 1440 }    # 24h
    action: warn
```

**Supported `match` keys**: `kind`, `name_contains`, `image_contains`, `cmdline_contains`, `idle_minutes_min`, `cpu_percent_max`.
**Supported actions**: `reap`, `warn`, `snooze` (with `snooze_minutes:` extra key).

The policy engine is consulted:
- in `apply_policies` (MCP) — the AI agent sees exactly what you've authorized
- in `idle-janitor reap` — defaults to `--only-policy` (reap only resources whose rule says `reap`)
- in the live TUI — each row shows its decision in color

---

## Example Input & Output

### CLI — `idle-janitor status`

```
──────────── idle-janitor • status ────────────
₹0.37, 46.8 Wh, 33.4 g CO₂ wasted on 3 idle resource(s) — a filter coffee's worth of grid energy.

┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━┳━━━━━━┳━━━━━━━┓
┃ Resource        ┃ Kind   ┃ Uptime ┃ CPU % ┃ Mem MB ┃  Wh ┃    ₹ ┃ g CO₂ ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━╇━━━━━━╇━━━━━━━┩
│ sleepy_postgres │ docker │ 2d 3h  │   0.1 │    124 │ 32.0│ 0.26 │  22.8 │
│ ngrok           │ process│ 1d 4h  │   0.0 │     18 │ 10.2│ 0.08 │   7.3 │
│ vite            │ process│    6h  │   0.0 │     82 │  4.6│ 0.03 │   3.3 │
└─────────────────┴────────┴────────┴───────┴────────┴─────┴──────┴───────┘
```

### MCP — `apply_policies(dry_run=True)` response

```json
{
  "dry_run": true,
  "decision_count": 3,
  "decisions": [
    {"resource_id": "docker:a1b2c3", "name": "sleepy_postgres", "kind": "docker",
     "rule": "protect", "action": "protect", "reason": "matched a protect clause"},
    {"resource_id": "proc:48213", "name": "ngrok", "kind": "process",
     "rule": "reap-stale-ngrok", "action": "reap",
     "reason": "idle for 68m ≥ 60m; name matches 'ngrok'"},
    {"resource_id": "proc:51209", "name": "vite", "kind": "process",
     "rule": "warn-stale-vite", "action": "warn",
     "reason": "idle for 240m ≥ 180m; name matches 'vite'"}
  ],
  "executed": []
}
```

### MCP — safe termination (`terminate_resource`)

Agent's first call: `terminate_resource(resource_id="proc:48213", dry_run=True)`
```json
{"ok": true, "dry_run": true,
 "would_terminate": {"id": "proc:48213", "pid": 48213, "name": "ngrok",
                     "cmdline": "ngrok http 8080 --region ap"}}
```

Agent confirms with human → calls with `dry_run=False`:
```json
{"ok": true, "terminated": {"id": "proc:48213", "pid": 48213, "name": "ngrok",
                            "cmdline": "ngrok http 8080 --region ap"}}
```

---

## How to Test

### Smoke test without an MCP client

```bash
source .venv/bin/activate
idle-janitor status
```

### Full demo (spawns 3 realistic fake dev servers for testing)

```bash
python demo_seed.py start               # spawn fakes: ngrok, vite, uvicorn
idle-janitor status                     # see all three listed, with ₹/Wh/CO₂
idle-janitor policies --evaluate        # watch decisions after enough minutes
idle-janitor live                       # ← the showstopper dashboard
# ... when done:
python demo_seed.py stop                # clean up
```

### Safety guard

```bash
python -c "from janitor import process_scan; print(process_scan.terminate(1, dry_run=True))"
# → {"ok": false, "error": "Refusing to terminate: process is not on the dev-server allowlist.", ...}
```

Even `dry_run=True` on `pid 1` (launchd) is refused.

---

## Known Limitations

- **Cost and watt numbers are estimates.** Per-resource watts come from a small static lookup table by image/process family (postgres ≈ 8 W, node ≈ 5 W, nginx ≈ 2 W, default 5 W). ₹ uses a flat ₹8/kWh (India residential average). CO₂ uses 0.713 kg/kWh (India grid, CEA 2024). This is intentional — the point is a *relatable* signal, not a scientific one. Each number is clearly labelled as an estimate in the headline.
- **v1 is Docker + local processes only.** Firebase emulators, cloud VMs (AWS/GCP), Vercel preview envs, and Supabase branches are on the roadmap. Kept offline + auth-free for v1 so the demo cannot be sabotaged by network / login flows.
- **Idle = low CPU right now.** We don't track long-horizon activity history for *idleness* (though we do track cumulative waste in SQLite). A background job that sleeps most of the time and wakes briefly may be flagged as idle between wakes. Snooze it.
- **Dev-server detection is pattern-based.** Covers ~25 common dev servers via regex word-boundary matches. Custom tooling may not be recognized — easy to extend in `janitor/process_scan.py::DEV_SERVER_PATTERNS`.
- **macOS + Linux expected to work.** Developed and tested on macOS; the Python stack (`psutil`, `docker`, `rich`, `typer`) is cross-platform. Windows is untested in this build.

---

## Security & Privacy Considerations

Security is **the** reason this project is interesting \u2014 you're giving an AI the ability to stop processes. Below is exactly what we do about it.

### Threat model

idle-janitor assumes:
- The MCP client (your AI assistant) may call tools with mistaken, hallucinated, or wrong arguments.
- A compromised or over-eager agent may try to loop-call destructive tools.
- A user may store secrets in dev-server command-line arguments (`node app.js --api-key=...`).
- A user may run alongside system processes (launchd, WindowServer, Cursor itself) that must never be touched.

idle-janitor does **not** try to defend against:
- A root-level attacker on your machine (they can bypass any userland guard).
- Deliberate misuse by the human user running the CLI as themselves.

### Layered guardrails (defense in depth)

Every destructive call goes through `janitor/safety.py::check_reap()`, which enforces **five independent layers** in order. A failure in any one layer refuses the action and journals the refusal.

| # | Layer | What it blocks |
|---|---|---|
| 1 | **Snooze** (`~/.idle-janitor/snooze.json`) | Anything the user said "leave this alone" to |
| 2 | **System blocklist** (`BLOCKLIST_NAMES` + system path prefixes) | `launchd`, `WindowServer`, `SystemUIServer`, `Cursor`, `zsh`, Chrome, Safari, anything under `/System/`, `/usr/libexec/`, `/Library/Apple/`, `/Library/PrivilegedHelperTools/`, `/Library/CoreMediaIO/`, `/usr/sbin/`, `/sbin/` |
| 3 | **Dev-server allowlist** (regex with `\b` word boundaries) | Anything whose cmdline doesn't look like a known dev server (`ngrok`, `vite`, `uvicorn`, `firebase emulators:start`, ~25 more). Processes with unreadable cmdlines are refused by default. |
| 4 | **Policy `protect` clauses** (`~/.idle-janitor/policies.yaml`) | Anything matching `protect:` \u2014 e.g., `image_contains: postgres`, `name_contains: production`. Checked server-side in `apply_policies` **and** in `terminate_resource`, so direct agent calls can't bypass it. |
| 5 | **Rate limiter** (default: 10 reaps / 60s rolling window) | Runaway loops. A hallucinating agent calling `terminate_resource` in a tight loop hits this instantly. |

### Dry-run everywhere

Every destructive tool, CLI, and watcher mode **defaults to no-op**:
- `terminate_resource(dry_run=True)` by default
- `apply_policies(dry_run=True)` by default
- `idle-janitor reap --dry-run` by default
- `idle-janitor agent --advisory` by default (no `--autonomous` = no action)

### Preview before you reap

Agents can \u2014 and should \u2014 call `safety_check(resource_id)` to preview the guard's verdict **without side effects**. Example response for `proc:1` (launchd):

```json
{
  "allowed": false,
  "reasons": [
    "process is on the system blocklist (name='launchd', exe='/sbin/launchd')"
  ],
  "rate_limit_remaining": 0
}
```

This lets the agent explain *why* an action was refused instead of surprising the user with a cryptic error.

### Audit log

Every reap attempt \u2014 **including refusals** \u2014 is journaled in `~/.idle-janitor/history.db` (`reap_log` table) with the resource id, outcome, and the guard reason. You can inspect it with `sqlite3 ~/.idle-janitor/history.db "select * from reap_log order by ts desc limit 20;"`.

### Secret redaction

Before writing to the journal or returning in an error message, we scrub likely-sensitive values from command lines:

| Pattern | Before | After |
|---|---|---|
| Flagged secrets | `node app.js --api-key=sk-live-abc` | `node app.js --api-key=***REDACTED***` |
| Space-separated | `python app.py --token foo-secret` | `python app.py --token ***REDACTED***` |
| URL creds (any scheme) | `mysql://root:supersecret@db:3306/app` | `mysql://root:***REDACTED***@db:3306/app` |
| Auth headers | `curl -H 'Authorization: Bearer xxx-xyz'` | `curl -H 'Authorization: Bearer ***REDACTED***'` |

See `janitor/safety.py::redact()`.

### What idle-janitor does NOT do

- **No network calls** anywhere. The Firebase adapter only talks to `127.0.0.1:4400` (hard-coded loopback IP, not `localhost` which could resolve elsewhere).
- **No credentials** read, written, or required.
- **No telemetry.**
- **No arbitrary code execution** \u2014 YAML is loaded with `yaml.safe_load`; policies cannot execute Python.
- **No cluster-wide operations** \u2014 `docker stop` is called on a specific container ID; never `docker kill -9` on everything.

### Verifying the guards yourself

```bash
# Must refuse pid 1 (launchd) with a specific reason
python -c "from janitor import safety; print(safety.check_reap('proc:1'))"

# Must refuse a non-dev-server (your shell, your editor)
python -c "import os; from janitor import safety; print(safety.check_reap(f'proc:{os.getppid()}'))"

# Must refuse anything in snooze
python -c "from janitor import safety, snooze; snooze.snooze('proc:1', 1); print(safety.check_reap('proc:1')); snooze.clear('proc:1')"

# Rate limiter smoke
python -c "
from janitor import safety
safety.configure_rate_limit(max_actions=2, window_seconds=5)
for _ in range(4):
    v = safety.check_reap('docker:xxx')
    if v.allowed: safety.record_action()
    print(v)
"
```

---

## Future Improvements

- [x] Firebase emulator adapter via the local hub.
- [x] Autonomous watcher (`idle-janitor agent`) that samples every N minutes and acts per policy.
- [x] macOS native notification when daily waste crosses a threshold.
- [x] AWS adapter (fixture-driven architecture; boto3 swap-in documented).
- [ ] Replace AWS fixture with real `boto3` + credential-handling review.
- [ ] GCP, Vercel preview envs, Supabase branches.
- [ ] Richer idle heuristics (network I/O, time since last `exec`, open socket count).
- [ ] `pip install idle-janitor` on PyPI.
- [ ] Configurable watts table + tariff via `.env`.

---

## License

This project is contributed under the repository's open-source license (MIT).

---

## Context

Built for **FORK. BUILD. MERGE.** at **DevFest 2026**, Bengaluru — a solo hack.

The one-line pitch:
> *"Your AI assistant can spin up a container. idle-janitor is how it finally learns to clean up after itself."*
