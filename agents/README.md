# AI Agents (`agents/`)

This directory houses community-contributed AI agents, multi-agent systems, and task-oriented assistants.

---

## Project V.U.L.C.A.N. Distributed Agent Swarm

The following Google ADK & A2A agent servers are hosted directly in this directory:

- **[`forensics_a2a_server.py`](forensics_a2a_server.py)** (Port 8001):
  - Google ADK `Agent(name="forensics_profiler_agent", model="gemini-3.8-flash")`
  - Runs `EXPLAIN QUERY PLAN` and `inspect_table_indexes` against SQLite `vulcan_demo.db` to produce forensic proof of N+1 loops and `SCAN TABLE bids`.
  - Exposes A2A Agent Card at `http://localhost:8001/.well-known/agent.json`.
- **[`finops_a2a_server.py`](finops_a2a_server.py)** (Port 8002):
  - Google ADK `Agent(name="finops_actuary_agent", model="gemini-3.8-flash")`
  - Calculates monetary blast radius for AWS Aurora Standard ($0.20/1M I/O requests) and Azure SQL Serverless ($0.5218/vCore-hour) at target RPS.
  - Exposes A2A Agent Card at `http://localhost:8002/.well-known/agent.json`.
- **[`vulcan_orchestrator.py`](vulcan_orchestrator.py)**:
  - Root Orchestrator using `RemoteA2aAgent` to communicate with both A2A endpoints.
  - Implements The Reforger: hot-patches repository code to single batched `LEFT JOIN`, generates `idx_bids_auction_id`, benchmarks improvements in sandbox, and provides 1-click rollback.

---

## Directory Index

| Agent File / Component | Description | Framework / Stack | Contributor |
| :--- | :--- | :--- | :--- |
| [`forensics_a2a_server.py`](forensics_a2a_server.py) | Forensics Profiler A2A Agent (:8001) | Google ADK, A2A Protocol, Gemini 3.8 Flash | Community Contributor |
| [`finops_a2a_server.py`](finops_a2a_server.py) | FinOps Actuary A2A Agent (:8002) | Google ADK, A2A Protocol, Gemini 3.8 Flash | Community Contributor |
| [`vulcan_orchestrator.py`](vulcan_orchestrator.py) | Root Orchestrator & Reforger Sandbox Verifier | Google ADK RemoteA2aAgent, SQLite Sandbox | Community Contributor |
