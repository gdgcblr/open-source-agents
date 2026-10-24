# incident-triage-agent-go

> An ADK-Go agent that takes a firing alert, pulls metrics from Prometheus and logs from Loki, checks them against known baselines, and drafts a root-cause report in which every claim cites the query that proves it.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: The first 15–30 minutes of most incidents go on the same mechanical checks: what exactly is broken, since when, did anything deploy, which errors are new, and which were always there. Under pressure, people blame the loudest error instead of the newest one.
- **Intended Users**: On-call engineers and SREs running Prometheus and Loki. It is also a reference for anyone building read-only, tool-using agents on ADK-Go.

### Key Features
- **Evidence-backed reports**: the report has a fixed shape (summary, root cause with confidence, evidence, ruled out, next steps), and every evidence bullet carries its PromQL or LogQL query.
- **Baseline-aware**: tools compare each signal with an earlier window and read a `baselines.yaml` of known noise, so steady-state errors are ruled out.
- **Victim vs. cause**: the procedure checks downstream dependencies before blaming the service that alerted.
- **Guardrails in code**, not only in the prompt: read-only tools, a tool-call budget, query validation, and secret/PII redaction before data reaches the model.
- **Observable**: each investigation streams its tool calls live and writes a JSON audit trail with timing and token usage.
- **Measured**: `eval.sh` injects four known faults into a lab and scores the agent.
- **Provider-agnostic**: Gemini by default, or any OpenAI-compatible server (Ollama, vLLM, llama.cpp) so data stays on your machine.

---

## Technical Stack
- **Language & Runtime**: Go 1.26.10+
- **Agent Framework**: [Google ADK for Go](https://github.com/google/adk-go) `v2.6.0`
- **Models**: Gemini (`gemini-flash-latest` by default), or a local open-weights model through an OpenAI-compatible API
- **Data sources**: Prometheus HTTP API, Loki HTTP API
- **Lab**: Docker Compose with Prometheus `v3.13.4`, Loki `3.7.9`, Grafana `12.4.12`, and a small Go demo shop

---

## Architecture & Data Flow

```
 alert (Prometheus) ──► triage agent (ADK-Go llmagent + Gemini)
                          │  BeforeTool: budget + query validation
                          │  AfterTool:  secret / PII redaction
                          ├─► get_firing_alerts     Prometheus /api/v1/alerts
                          ├─► list_metrics          metric catalogue
                          ├─► prom_query_summary    min/avg/max/last + change point
                          ├─► compare_to_baseline   now vs. N minutes ago, verdict
                          ├─► log_patterns          Loki: errors by message, new vs. steady
                          ├─► recent_changes        deploys (build_info) + restarts
                          └─► known_baselines       baselines.yaml
                          ▼
                Markdown report  +  runs/<name>.json audit trail
```

The tools do the arithmetic in Go and return summaries, never raw datapoints, so the model spends its tokens on reasoning. The instructions encode an on-call procedure: find the symptom, quantify it, separate victim from cause, check changes, check logs while ignoring baseline noise, check resources, then confirm against the baseline.

### The lab (`lab/`)
A two-service shop (`checkout` → `payments`) with fault switches, so every incident has a known root cause:

| `./lab/chaos.sh …` | True root cause | What it tests |
| :--- | :--- | :--- |
| `latency` | payments is slow (+1.5 s) | Both services alert; checkout is only the victim |
| `bad-deploy` | checkout v1.4.0 throws 500s in `applyCoupon` | Linking a deploy to the error spike |
| `pool` | checkout DB connection pool exhausted (503) | Ignoring the loud, always-on payments error |
| `leak` | checkout leaks memory and gets OOM-killed | Resource metrics and restarts, not errors |

`payments` always logs ~300 `exchange-rate refresh failed` errors per minute. That is the red herring: it is loud, but it is in `baselines.yaml` and its trend is steady.

---

## Prerequisites
- Go 1.26.10+ (`go version`)
- Docker with Compose v2
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey), **or** an OpenAI-compatible model server such as [Ollama](https://ollama.com)

---

## Installation & Setup

```bash
cd agents/incident-triage-agent-go

# 1. Start the lab (first build takes a few minutes)
docker compose -f lab/docker-compose.yml up -d --build

# 2. Configure the model
cp .env.example .env        # then put your key in .env
```

Grafana is at http://localhost:3000 (anonymous, read-only use), Prometheus at http://localhost:9090.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | Yes, for Gemini | *None* | Gemini API key |
| `MODEL_PROVIDER` | No | `gemini` | `gemini` or `openai` (any OpenAI-compatible server) |
| `MODEL_NAME` | No | `gemini-flash-latest` / `qwen3:8b` | Model identifier |
| `OPENAI_BASE_URL` | No | `http://localhost:11434/v1` | OpenAI-compatible endpoint (Ollama default) |
| `PROMETHEUS_URL` | No | `http://localhost:9090` | Prometheus to query |
| `LOKI_URL` | No | `http://localhost:3100` | Loki to query |
| `BASELINES_FILE` | No | `baselines.yaml` | Known steady-state noise |
| `MAX_TOOL_CALLS` | No | `20` | Tool-call budget per investigation |

---

## How to Run

```bash
# Break something, wait ~1 minute for the alert to fire
./lab/chaos.sh latency

# One-shot investigation: live tool calls on stderr, report on stdout
go run . triage -trace runs/latency.json

# Or give it a specific alert / question
go run . triage "checkout p99 latency is above 500ms, why?"

# Interactive: ADK web UI (port 8000; the lab uses 8080)
go run . web -port 8000 api webui

# Put the lab back to normal
./lab/chaos.sh reset
```

---

## Example Input & Output

### Example Input
```bash
./lab/chaos.sh latency
go run . triage "Triage the alerts that are firing right now."
```

### Example Output
_To be replaced with a real run before merge (`runs/latency.md`)._

---

## How to Test

```bash
./eval.sh            # all four scenarios, about 4 minutes each
./eval.sh latency    # a single scenario
```

For each scenario `eval.sh` resets the lab, waits for alerts to clear, injects the fault, waits for an alert, runs one triage, and passes if the *Most likely root cause* section names the right service and cause without blaming the known noise. Reports and traces land in `runs/`.

---

## Known Limitations
- The lab's `compare_to_baseline` default (30 min back) needs the lab running for 35+ minutes. On a fresh lab, ask for a shorter offset.
- `recent_changes` infers deploys from a `build_info{version=…}` metric. Services without one only show restarts.
- Small local models (≤8B) follow the procedure less reliably than Gemini Flash.
- Logs must be JSON with a `msg` field for `log_patterns` to group them. Other formats need a different LogQL parser stage.
- The model only sees redacted tool output, but the redaction is regex-based and not a guarantee.

---

## Security & Privacy Considerations

- **Secrets Handling**: The API key is read from the environment or a git-ignored `.env`. Nothing is hard-coded.
- **Read-only by construction**: tools only issue HTTP GETs to the configured Prometheus and Loki. There is no shell, no file writes beyond the optional trace, and no remediation.
- **Guardrails** (`guardrails.go`, ADK tool callbacks):
  - a tool-call budget per investigation (default 20), after which the model must write its report;
  - query validation: maximum length, lookback ≤ 24h, and no match-everything selectors;
  - redaction of emails, card-like numbers, bearer tokens, API keys and JWTs from every tool result before it reaches the model.
- **Bounded cost and time**: 15 s per data query, an 8 MB response cap, at most 10 series per result, 90 s per model call with retries on 429/5xx, and an overall `-timeout` (default 4 min).
- **Prompt injection**: log lines are treated as untrusted data, and the instructions forbid following instructions found in them.
- **Data Privacy**: With Gemini, redacted metric summaries and log samples go to Google's API. With `MODEL_PROVIDER=openai` and a local server, nothing leaves the machine.

---

## Future Improvements

- [ ] Alertmanager webhook receiver, so triage starts automatically when an alert fires
- [ ] Specialist sub-agents (metrics, logs, changes) under a coordinator
- [ ] BigQuery as an alternative log source behind the same `log_patterns` contract
- [ ] Trace data (Tempo/Jaeger) for request-level evidence

---

## License

*This project is contributed under the repository's open-source license.*
