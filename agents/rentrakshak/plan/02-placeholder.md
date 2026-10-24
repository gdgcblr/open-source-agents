# 02 — Architecture & data schemas

**Modules:**
- `rentrakshak/models/` — Pydantic I/O for tools and API
- `rentrakshak/db/` — SQLite schema, parameterized queries
- `rentrakshak/data/` — rent comparables JSON, Karnataka legal sources JSON
- `rentrakshak/guardrails/` — deterministic moderation + optional Model Armor hook
- `rentrakshak/services/` — business logic (no LLM authority on security)
- `rentrakshak/tools/` — ADK `FunctionTool` wrappers
- `rentrakshak/agent.py` — `root_agent` for ADK CLI

**Principle:** LLM orchestrates; tools compute, persist, and enforce policy.
