# Secure Agent Harness

The Secure Agent Harness is an AI agent framework that allows an LLM to perform tasks using tools while controlling what it can access, what it can remember, how much it can spend, and which actions it is allowed to execute.

Think of it as a secure operating system for an AI agent. The LLM is the brain; the harness is the control layer around it.

A self-contained, security-first Python agent starter for `agents/` in the `open-source-agents` repository.

It demonstrates an agent harness with bounded tool execution, input/output guardrails, scoped SQLite memory, context injection, cost/step limits, audit events, and an optional Jev-style typed decision interface.

> **Security note:** This is a starter implementation, not a security certification. Prompt-injection detection is heuristic and cannot guarantee detection. Keep tools least-privileged, isolate runtime infrastructure, and require human approval for consequential actions.


## Architecture Overview

![Secure Agent Harness Architecture](../../pics/Screenshot%202026-10-24%20125448.png)

- **Harness loop:** bounded model/tool loop, explicit tool registry, validated arguments, no arbitrary shell or Python execution.
- **Guardrails:** request size limits, secret redaction before audit, output length cap, policy checks, strict tool schemas.
- **Memory:** SQLite facts scoped by `user_id`, with explicit write operations and retention limit.
- **Context injection:** deterministic system policy + scoped memory + request-local context; external context is labelled untrusted.
- **Jev-style decision seam:** typed `allow / review / block` decision contract and deterministic local implementation. This is an integration seam, **not an official Jev API client**.
- **Cost controls:** maximum steps, request size, tool calls, output tokens, and estimated session budget.
- **Security/observability:** structured audit events without storing full prompts or secrets.
- **Tests:** unit tests for guardrails, tool authorization, and memory isolation.

## Architecture

```text
User request
   |
   v
Input guardrails -----> reject / redact sensitive audit fields
   |
   v
Context builder <---- scoped SQLite memory
   |
   v
LLM planner (proposes only)
   |
   v
Decision gate (allow / review / block)
   |
   v
Tool registry -> schema validation -> permission check -> execution
   |                                             |
   +---------------- result ---------------------+
   |
   v
Output guardrails -> answer + audit metadata
```

## Folder structure

```text
agents/secure-agent-harness/
├── README.md
├── .env.example
├── .gitignore
├── pyproject.toml
├── src/
│   └── secure_agent_harness/
│       ├── __init__.py
│       ├── agent.py          # bounded agent control loop
│       ├── audit.py          # privacy-aware structured audit
│       ├── config.py         # typed environment configuration
│       ├── context.py        # trusted instructions + scoped context
│       ├── cost.py           # usage estimates and budget enforcement
│       ├── decision.py       # typed decision interface / Jev seam
│       ├── guardrails.py     # request, policy, and response checks
│       ├── memory.py         # isolated SQLite memory
│       ├── models.py         # shared data contracts
│       └── tools.py          # allowlisted, schema-validated tools
└── tests/
    ├── test_guardrails.py
    ├── test_memory.py
    └── test_tools.py
```

## Requirements

- Python 3.11+
- An OpenAI API key for live model calls
- Internet access to reach the configured model API

## Installation

From the repository root:

```bash
cd agents/secure-agent-harness
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
python -m pip install -e ".[dev]"
```

macOS/Linux:

```bash
source .venv/bin/activate
cp .env.example .env
python -m pip install -e ".[dev]"
```

Set `OPENAI_API_KEY` in `.env`. Never commit `.env`.

## Run

```bash
secure-agent
```

Or:

```bash
python -m secure_agent_harness
```

The CLI accepts one request at a time. Example: `What is 19 * 23?` or `Remember that my preferred language is Python.` Memory is scoped to the configured local user ID.

## Configuration

See `.env.example`. Important controls:

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Provider secret |
| `OPENAI_MODEL` | Model name supported by your account |
| `MAX_STEPS` | Maximum model/tool loop iterations |
| `MAX_TOOL_CALLS` | Maximum tools executed per request |
| `MAX_INPUT_CHARS` | Request size cap |
| `MAX_OUTPUT_TOKENS` | Model output token cap |
| `MAX_ESTIMATED_COST_USD` | Conservative session budget estimate |
| `MEMORY_DB_PATH` | SQLite file path |
| `AGENT_USER_ID` | Local memory namespace |

The cost estimate uses configurable per-million-token rates. Update those rates for the model/provider you actually use. Estimates are guardrails, not billing-grade accounting; provider usage data is authoritative.

## Security design decisions

1. **No arbitrary code execution.** The model can only call registered tools.
2. **Validate at execution time.** Tool names, arguments, limits, and permissions are checked in Python, not entrusted to the model.
3. **Least privilege.** The included tools are read-only calculator/time utilities plus an explicit memory write. Add integrations individually and scope their credentials.
4. **Untrusted context stays untrusted.** Retrieved facts and user content are labelled as data, never promoted to system instructions.
5. **Memory isolation.** Reads and writes require a user namespace. Do not use a shared default user ID in a multi-user service.
6. **No secrets in logs.** Audit records contain event metadata, not complete prompts, responses, or tool arguments.
7. **Bounded execution.** Step, tool-call, input, output, and estimated-cost budgets prevent runaway loops.
8. **Human approval.** Consequential tools should declare `requires_approval=True` and be blocked unless a trusted approval mechanism supplies approval. Do not let the model approve its own actions.
9. **Prompt injection is not solved by a classifier.** Keep data access and side effects restricted even if detection fails.
10. **Production hardening.** Add authentication, per-user rate limits, secret management, encrypted storage, network egress policy, sandboxing, retention controls, and independent monitoring before exposing this as a service.

## Jev integration

`decision.py` defines a small typed contract (`Decision`, `DecisionGate`) and ships a deterministic local gate. This makes routing and safety decisions measurable and testable without coupling the project to a provider-specific SDK.

To use Jev, implement a separate adapter against the **current official Jev/TypeSafe API documentation**, map its typed result into `Decision`, and retain the local policy checks as authoritative enforcement. Never use Jev confidence alone to authorize a sensitive action, and never give the decision layer tool permissions.

## Tests

```bash
pytest
```

Tests do not require an API key.

## Before opening a pull request

- [ ] Read `../CONTRIBUTING.md`.
- [ ] Run `pytest`.
- [ ] Verify installation from a clean virtual environment.
- [ ] Confirm `.env`, database files, logs, and virtual environments are ignored.
- [ ] Add tests for every new tool and every permission boundary.
- [ ] Document any external service, credentials, costs, and data retention.
- [ ] Do not claim the agent is injection-proof or production-secure without independent validation.
