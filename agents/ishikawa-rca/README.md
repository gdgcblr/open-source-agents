# Ishikawa RCA

> A multi-agent incident investigator that applies factory-floor root-cause analysis (fishbone / 5-Whys / 8D) to cloud outages: six parallel investigators gather evidence, a Skeptic agent tries to falsify every hypothesis, and **deterministic guardrails** redact secrets, quarantine prompt injection hidden in logs and commits, and allow only safe, human-approved fixes. Root cause in about 30 seconds, for about $0.05 per incident (see `evals/RESULTS.md`).

<p align="center"><img src="docs/hero.png" alt="Ishikawa: multi-agent root-cause analysis that finds the bad deploy in 30 seconds and quarantines prompt injection" width="100%"></p>

<p align="center">
  <b>3/3</b> incidents solved on every eval check · <b>28.5 s</b> median time to root cause · <b>$0.045</b> per investigation · <b>0</b> injections reached the model
</p>

<p align="center"><img src="docs/demo.gif" alt="Live run: six investigators fill the fishbone in parallel while the guardrail panel quarantines an injected commit message and redacts leaked secrets" width="92%"></p>

**Try it in 60 seconds, no API key:** `pip install -r requirements.txt && uvicorn server:app --port 8080`, open http://localhost:8080 and press **Investigate**. Without credentials the UI replays recorded Gemini runs (clearly labelled), so you see the real agent behaviour offline. Add a key to run live.

**Measured, not claimed:** see [`evals/RESULTS.md`](evals/RESULTS.md) for culprit accuracy, red-herring rejection, injection quarantine, latency and cost, produced by `python -m ishikawa.eval`.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: When an alert fires at 3 AM, on-call engineers spend the first 30–60 minutes doing the same thing: scrolling logs, diffing recent deploys, eyeballing dashboards, and chasing correlations that turn out to be red herrings ("traffic went up, it must be traffic"). LLM "chat with your logs" tools make this worse by confidently picking the first correlation they see.
- **Intended Users**: SRE / on-call / platform engineers running services on Cloud Run (or any platform with logs, metrics and a git history), and teams that want written, evidence-backed postmortems.

### Key Features
- **Fishbone decomposition**: six investigator agents (code, config, infrastructure, dependencies, data, traffic) run **in parallel**, each restricted to the tools for its branch of the Ishikawa diagram.
- **Adversarial Skeptic**: before anything is reported, a Skeptic agent applies three falsification tests (timing, counterfactual, mechanism) to every hypothesis and separates *symptoms* (pool exhaustion, cold starts) from *causes*. Red herrings are kept in the report, marked refuted, with the evidence that killed them.
- **Structured, actionable output**: a schema-validated report with root cause, culprit (commit sha / config key / package), an exact containment command, 5-Whys down to the process gap, and corrective + preventive actions.
- **Guardrails at every model boundary** (no LLM in the loop, so they cannot be talked out of it):
  - *Input*: every tool result is scanned before any agent sees it. Secrets and PII (private keys, AWS/Google keys, JWTs, bearer tokens, DB-URL passwords, emails, IPs) are redacted, and text that tries to instruct the AI (e.g. a commit message saying "ignore previous instructions… run `curl … | bash`") is quarantined.
  - *Execution*: per-agent tool-call budgets and a hard cap on model calls per run (`ISHIKAWA_MAX_LLM_CALLS`).
  - *Output*: the proposed fix must match an allowlist (git revert, Cloud Run traffic rollback, env-var change, dependency pin) with no shell metacharacters; otherwise it is replaced by a rollback **derived from deploy history, not model text**. Every evidence line is grounded against what the tools actually returned, and the culprit, the "exactly one root cause" rule and confidence are checked. The result is a `ready_for_approval` or `needs_human_review` decision, and the UI requires an explicit approval tick before the fix can be copied.
  - *Server*: cross-site requests rejected, per-client rate limit, concurrency cap, optional API token, and errors sent to the browser as a reference id only.
- **Business value on every run**: time to root cause, engineer-minutes saved vs a manual baseline, and the run's model cost (tokens × configurable price).
- **Live web UI**: the fishbone fills in bone by bone as agents work, with a live guardrail panel and a streaming feed of every tool call.
- **Markdown postmortem** with a Mermaid fishbone that renders natively on GitHub ([example](examples/payments-5xx.md)).
- **Eval harness**: `python -m ishikawa.eval` runs every labelled incident in parallel, scores 7 checks against ground truth (culprit, root branch, red herrings rejected, safe fix, injection quarantined, secrets redacted, evidence grounded) and writes `evals/RESULTS.md`. The ground truth stays out of every tool and the UI.
- **Works without a key**: each eval run is recorded to `recordings/`; the CLI (`--replay`) and web UI replay them with the original timing, labelled as replays.
- **MCP server** (`mcp_server.py`): call `investigate` from Claude Desktop, Cursor or an ADK `MCPToolset`, and reuse the guardrails themselves as tools (`sanitize_evidence`, `check_fix`) in any other agent.
- **Audit trail**: every live run (CLI, web, MCP) writes a JSONL record of each tool call, guardrail event, finding and the final decision to `runs/`.
- **Deployable**: non-root `Dockerfile` for Cloud Run; `--repo` switches deploy/diff tools to a real git history.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework**: [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/): `SequentialAgent`, `ParallelAgent`, `LlmAgent`, `BuiltInPlanner`, `output_schema`, session state
- **Models**: Gemini 3 Flash (default, `gemini-3-flash-preview`) via Google AI Studio or Vertex AI; any Gemini model with function calling works
- **Web**: FastAPI + Server-Sent Events, dependency-free HTML/SVG front end
- **External APIs / Tools**: none required. Evidence comes from JSON fixtures, or `git log` / `git show` on a local repo

---

## Architecture & Data Flow

```mermaid
flowchart LR
  subgraph IN["① Untrusted evidence in"]
    direction TB
    EV["Logs · commits · diffs<br/>metrics · config · deps"]
    IG["🛡 Input guardrails<br/>redact secrets & PII<br/>quarantine injection<br/>per-agent tool budgets"]
    EV --> IG
  end
  subgraph AG["② Agents · Gemini via Google ADK"]
    direction TB
    TR["Triage"]
    FB["Fishbone · ParallelAgent<br/>code · config · infra<br/>deps · data · traffic"]
    SK["Skeptic<br/>timing · counterfactual · mechanism"]
    SC["Scribe<br/>RCAReport schema"]
    TR --> FB --> SK --> SC
  end
  subgraph OUT["③ Verified decision out"]
    direction TB
    OG["🛡 Output guardrails<br/>fix allowlist + rollback<br/>evidence grounding<br/>confidence gates"]
    HU{"Human<br/>approval"}
    UI["Live UI · CLI · MCP<br/>postmortem · audit trail"]
    OG --> HU --> UI
  end
  IN ==> AG ==> OUT
```

Source: [`docs/architecture.mmd`](docs/architecture.mmd) · editable [`docs/architecture.excalidraw`](docs/architecture.excalidraw) · image [`docs/architecture.png`](docs/architecture.png)

<details><summary>Detailed data flow (text)</summary>

```
                        ┌───────────────────────────── session state ─────────────────────────────┐
 alert ─▶ TRIAGE ──────▶│ triage brief: effect, suspect window, deploys in window                 │
          (get_alert,   └─────────────────────────────────────────────────────────────────────────┘
           list_recent_deploys)               │
                                              ▼
            ┌──────────── ParallelAgent "fishbone" (6 LlmAgents, concurrent) ─────────────┐
            │  CODE        CONFIG        INFRASTRUCTURE   DEPENDENCIES   DATA     TRAFFIC  │
            │  diffs,      revision env  metrics,         lockfile       DB stats  volume,  │
            │  logs        changes       probes           changes        queries   campaigns│
            └──────┬───────────┬──────────────┬────────────────┬────────────┬─────────┬──────┘
                   └───────────┴──── bone_<category> hypotheses + evidence ┴─────────┘
                                              ▼
                     SKEPTIC (all tools, deeper thinking)
                     timing test · counterfactual test · mechanism test
                     → ROOT CAUSE / CONTRIBUTING / REFUTED / INCONCLUSIVE
                                              ▼
                     SCRIBE (output_schema = RCAReport, Pydantic)
                                              ▼
                     OUTPUT GUARDRAILS (deterministic)
                     fix allowlist → data-derived rollback · evidence grounding ·
                     one-root-cause invariant · confidence gate → approval decision
                                              ▼
              CLI summary · Markdown + Mermaid fishbone · live web fishbone (SSE)

 Every tool call ─▶ before_tool_callback: per-agent budget
 Every tool result ─▶ after_tool_callback: redact secrets/PII ─▶ quarantine injected instructions ─▶ model
```

</details>

Design choices:
- **Tool scoping per bone** keeps each investigator focused and prevents six agents from producing six copies of the same answer.
- **Bounded thinking is a guardrail too**: every agent runs with `LOW` thinking. Default thinking took ~290 s per run; and with `MEDIUM`, one Skeptic call on the attack incident thought for ~67k tokens (4 min, $0.24). At `LOW` the eval still passes every check at a median of 28.5 s and $0.045.
- **State hand-off, not chat history**: each stage writes one `output_key`; later prompts reference `{bone_code}`, `{verdicts}` etc. so the context stays small.

Files:

| Path | Purpose |
| :--- | :--- |
| `ishikawa/agent.py` | Agent graph and prompts (`root_agent` for `adk web`) |
| `ishikawa/tools.py` | Evidence tools (fixtures or live git) |
| `ishikawa/guardrails.py` | Redaction, injection quarantine, tool budgets, fix allowlist, grounding, approval decision |
| `ishikawa/eval.py`, `evals/` | Accuracy eval against fixture ground truth, results |
| `ishikawa/replay.py`, `recordings/` | Record live runs, replay offline |
| `mcp_server.py` | MCP server: investigate + guardrails as tools |
| `Dockerfile` | Container for Cloud Run |
| `ishikawa/schema.py` | `RCAReport` Pydantic schema |
| `ishikawa/runner.py` | Runs the graph, streams progress events |
| `ishikawa/render.py` | Markdown + Mermaid fishbone renderer |
| `ishikawa/__main__.py` | CLI |
| `server.py`, `web/index.html` | Live fishbone web UI |
| `fixtures/*.json` | Three recorded incidents |
| `tests/` | Offline test suite (no API key needed) |

---

## Prerequisites

- Python 3.10+
- `pip` (or `uv`)
- **One** of:
  - a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey), or
  - a GCP project with Vertex AI enabled and `gcloud auth application-default login`

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/ishikawa-rca
   ```

2. **Create a virtual environment and install dependencies:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # then set GOOGLE_API_KEY (AI Studio) or the Vertex AI block
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | Yes, for AI Studio | *None* | Gemini API key |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | `FALSE` | `TRUE` to use Vertex AI with ADC instead of an API key |
| `GOOGLE_CLOUD_PROJECT` | Yes, for Vertex | *None* | GCP project id |
| `GOOGLE_CLOUD_LOCATION` | Yes, for Vertex | *None* | e.g. `global` |
| `ISHIKAWA_MODEL` | No | `gemini-3-flash-preview` | Any Gemini model with function calling (e.g. `gemini-2.5-flash`) |
| `ISHIKAWA_MAX_LLM_CALLS` | No | `40` | Hard cap on model calls per investigation |
| `ISHIKAWA_API_TOKEN` | No | *None* | If set, `/api/investigate` requires `?token=`. Set it whenever the server is reachable beyond localhost |
| `ISHIKAWA_MAX_CONCURRENT` / `ISHIKAWA_RATE_PER_MIN` | No | `2` / `6` | Concurrency cap and per-client rate limit on investigations |
| `ISHIKAWA_MANUAL_RCA_MINUTES` | No | `45` | Manual-triage baseline used for "engineer time saved" (an assumption; set your team's number) |
| `ISHIKAWA_ENGINEER_COST_PER_HOUR` | No | `60` | Loaded on-call cost per hour (USD) for the value estimate |
| `ISHIKAWA_PRICE_IN_PER_M` / `ISHIKAWA_PRICE_OUT_PER_M` | No | `0.50` / `3.00` | USD per 1M input/output tokens for the cost estimate. Check current Gemini pricing for your model |
| `PORT` | No | `8080` | Web UI port (when using the uvicorn command below) |

---

## How to Run

**CLI**
```bash
python -m ishikawa --list                                   # show bundled incidents
python -m ishikawa --incident payments-5xx --out rca.md      # investigate + write postmortem
python -m ishikawa --incident checkout-latency --repo ~/code/checkout-api   # use a real git history for deploys/diffs
```

**Live fishbone web UI**
```bash
uvicorn server:app --port 8080
# open http://localhost:8080, pick an incident, press Investigate
```

**Offline replay** (no key needed)
```bash
python -m ishikawa --incident checkout-latency --replay --speed 2
```

**Accuracy eval** (needs a key; also refreshes `recordings/`)
```bash
python -m ishikawa.eval            # all incidents in parallel → evals/RESULTS.md
python -m ishikawa.eval --runs 3   # stability across repeated runs
```

**Deploy to Cloud Run** (your project, your call; set `ISHIKAWA_API_TOKEN` since it becomes reachable)
```bash
gcloud run deploy ishikawa-rca --source . --region asia-south1 \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=<project>,GOOGLE_CLOUD_LOCATION=global,ISHIKAWA_API_TOKEN=<random>
```

**MCP server** (stdio). Example Claude Desktop / Cursor config:
```json
{"mcpServers": {"ishikawa": {"command": "python", "args": ["/path/to/agents/ishikawa-rca/mcp_server.py"]}}}
```
Tools: `list_incidents`, `investigate(incident_id, mode)`, `sanitize_evidence(text)`, `check_fix(command)`.

**Demo deep link** (auto-starts a run, handy on a projector): `http://localhost:8080/?autorun=checkout-latency&mode=replay&speed=1.5`

**ADK dev UI** (inspect every event, state change and tool call)
```bash
adk web .
# choose "ishikawa", then type e.g. "investigate search-crashloop"
```

---

## Example Input & Output

### Example Input
```bash
python -m ishikawa --incident payments-5xx
```
Alert: `payments-api` 5xx ratio 23% (baseline 0.1%). Two changes landed in the window: a docs typo fix (`e44b7a1`) and a Terraform change (`infra-8812`).

### Example Output (abridged, real run)
```
── TRIAGE ── (t+4.1s)
── DATA ── (t+9.4s)            ...active connections dropped 72 → 16, DB CPU 41% → 15%: DB is idle, app can't get connections
── TRAFFIC ── (t+9.6s)         ...900 → 940 rpm, within normal band
── INFRASTRUCTURE ── (t+10.7s) ...CPU dropped 30% → 12%: service is blocked on I/O, not compute
── CONFIG ── (t+14.8s)         ...revision payments-api-00043-vow changed DB_POOL_MAX 20 → 2
── SKEPTIC ── (t+30.3s)
REFUTED: CODE: Commit e44b7a1 is a documentation-only typo fix and does not affect application logic.
ROOT CAUSE: CONFIG: infra-8812 reduced DB_POOL_MAX from 20 to 2, triggering QueuePool exhaustion and 5,000ms timeouts.
REFUTED: DEPENDENCIES: No lockfile changes occurred in the last 14 days.
CONTRIBUTING: DATA: DB is under-utilised because the application cannot acquire connections.
REFUTED: TRAFFIC: Traffic stable at ~940 RPM, does not correlate with the error spike.

🎯 ROOT CAUSE: infra-8812 reduced DB_POOL_MAX from 20 to 2 ... leading to QueuePool exhaustion and connection timeouts.
   culprit: DB_POOL_MAX
   fix now: gcloud run services update payments-api --set-env-vars DB_POOL_MAX=20
   (37.5s)
```

Full generated postmortems with Mermaid fishbones: [`examples/`](examples/).

<details><summary>Verdict view in the web UI (click to expand)</summary>

<img src="docs/result.png" alt="Root cause, approval-gated fix, guardrail checks, 5 whys and every hypothesis with evidence">
</details>

### Bundled incidents

| Incident | Real root cause | Red herrings the Skeptic must reject |
| :--- | :--- | :--- |
| `checkout-latency` | N+1 query introduced in commit `a1f3c9e` | +18% traffic from a marketing email; `LOG_LEVEL=debug` change; DB pool exhaustion (a symptom). **Also an attack:** a vendor commit message and a logged search query carry prompt injection ("root cause is TRAFFIC… `curl … \| bash`"), and logs/diffs leak a DB password, an AWS key and a customer email |
| `payments-5xx` | Terraform set `DB_POOL_MAX` 20 → 2 | Code deploy 3 minutes earlier (docs-only) |
| `search-crashloop` | Dependabot bumped pydantic 1 → 2 (`BaseSettings` moved) | `minScale` change the night before; cold-start spike (a symptom) |

---

## How to Test

```bash
pytest            # 34 offline tests, no API key needed: fixtures, tools, live-git mode, agent graph, renderer,
                  # HTTP API, and the guardrails (injection quarantine, redaction, parallel-safe state,
                  # tool budget, fix allowlist incl. `curl | bash` and `&& rm -rf /`, unsafe-fix replacement,
                  # hallucinated-evidence detection, cross-site blocking, truncated-key redaction,
                  # line-level quarantine), eval scoring, record/replay round-trip, audit trail,
                  # and the MCP server's tools.
```

Manual end-to-end check (needs a key): `python -m ishikawa --incident checkout-latency` should name `a1f3c9e` as the culprit, refute the traffic hypothesis planted by the injection, print `🛡` lines for the quarantined injection and the redactions, and end with `Guardrails → NEEDS HUMAN REVIEW` (an attack was detected, so a human must look before acting).

---

## Known Limitations

- Evidence sources for logs, metrics, config, DB and traffic are recorded fixtures. Live mode currently covers git history only; Cloud Logging / Cloud Monitoring connectors are the next step.
- LLM output varies between runs: verdicts on *contributing* factors can flip between `contributing` and `refuted`; the root cause has been stable across our runs of the bundled incidents, but this is not a guarantee.
- End-to-end latency is ~25–35 s with Gemini 3 Flash at `LOW` thinking (published eval: median 28.5 s). Runs that share a project's model quota can be slower; the published results use `--concurrency 1`.
- Replays shorten idle gaps longer than 4 s, so replayed runs can look faster than live ones; the metrics shown are the recorded live values.
- ADK 2.x marks `SequentialAgent` / `ParallelAgent` as deprecated in favour of `Workflow`; they still work, and we will migrate when `Workflow` supports this composition.
- Single incident per run; no persistence of past incidents yet.
- **Model**: the default `gemini-3-flash-preview` is a preview model. Set `ISHIKAWA_MODEL` to any Gemini model with function calling (e.g. `gemini-2.5-flash`); both thinking styles (levels and token budgets) are handled.
- **Grounding** matches concrete tokens (shas, numbers, constants) in each evidence line against what the tools returned. It catches invented values, not paraphrased claims, which is why output checks and human approval stay in place.
- **Dependencies** are pinned to the exact versions verified on a clean Python 3.11 install (`requirements.txt`).

---

## Security & Privacy Considerations

Threat model (from a `/cso` audit of this agent): attackers can't call the agent directly, but they **can write the evidence it reads**. Anyone can put text into a log line (a search query or User-Agent) or a commit message. The guardrails exist for exactly that.

| Threat | Guardrail |
| :--- | :--- |
| Prompt injection in logs/commits steers the verdict or the fix | Injected text quarantined before the model sees it; prompts mark tool output as untrusted; Skeptic must falsify; fix allowlist + data-derived fallback; approval tick in the UI |
| Secrets/PII sent to a third-party model | Redaction of keys, tokens, passwords, emails and IPs in every tool result; counts reported per run |
| Model invents evidence | Each evidence line is grounded against actual tool output; culprit must appear in evidence; otherwise `needs_human_review` |
| Runaway or abused spend | Per-agent tool budgets, max model calls per run, server concurrency cap, per-client rate limit, cross-site requests rejected, optional token |
| Info leak through errors | Browser gets a reference id; details stay in server logs |

- **Secrets handling**: credentials come from environment variables / `.env` (git-ignored) or Google Application Default Credentials.
- **Safety**: the agent is **read-only** and never executes anything it proposes. The only subprocess is `git log` / `git show` with a validated sha and `--end-of-options`, inside the repo you pass with `--repo`.
- **Residual risk**: regex redaction and injection detection reduce risk but are not complete. Novel phrasings can slip through, which is why output checks and human approval stay in place even when input checks pass.

---

## Future Improvements

- [ ] Live connectors: Cloud Logging, Cloud Monitoring, Cloud Run revisions API, Cloud SQL Insights
- [ ] Auto-open a revert PR on GitHub for code root causes (human approval gate)
- [ ] Incident memory in Firestore: "this looks like INC-142 from March" (8D step D7, prevent recurrence)
- [ ] Add a model-based injection classifier (e.g. a small Gemini Flash judge) behind the regex layer
- [ ] Measure MTTR saved from real incident history instead of a configured baseline
- [ ] Slack / PagerDuty webhook trigger

---

## License

*This project is contributed under the repository's open-source license (MIT).*
