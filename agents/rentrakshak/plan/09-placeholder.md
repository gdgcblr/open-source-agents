# 09 — ADK agent integration

**Implement:**
- Register all tools on `root_agent` in `agent.py`
- Instructions: RentRakshak scope, untrusted listings, never claim verification, use tools for facts
- Model: `gemini-2.0-flash` via env `GOOGLE_API_KEY`; document Gemma via Vertex optional path
- `main.py` — deterministic safety report CLI (no API key)

**Tests:** `tests/test_agent_tools.py`
