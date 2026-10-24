# RentRakshak — Judging overview (read this first)

One-page narrative for evaluators who may not run the code immediately.

## Elevator pitch

**RentRakshak** helps Bengaluru renters **before they pay a deposit**. It combines a **Google ADK** agent with **deterministic** safety tools, an **anonymous tenant community**, and a **vacating-room board**—so the demo is a product, not a generic chat wrapper.

**Tagline:** Rent smarter. Stay safer. Help the next tenant.

## Five headline features

1. **Rental safety agent** — structured report from listing + chat; rule IDs, severities, evidence excerpts, verification steps.  
2. **Rent estimator** — min/median/max from versioned JSON; says when data is insufficient instead of guessing.  
3. **Anonymous experiences** — moderated posts; PII redaction; negative-but-fair reviews allowed.  
4. **Vacating board** — active/filled/expired lifecycle; contact kept private in MVP.  
5. **Karnataka checklist** — practical steps + legal source links; no invented deposit cap.

## Differentiators for scoring

| Criterion | Evidence in repo |
|-----------|------------------|
| **Google ADK depth** | `rentrakshak/agent.py`, `adk_agent/`, 13 `FunctionTool`s |
| **AI safety** | `guardrails/content_safety.py`, injection in fixtures, 32 tests |
| **Responsible claims** | Limitations on every report; low risk ≠ verified |
| **Real persistence** | SQLite schema for experiences & vacating posts |
| **Reproducibility** | `pytest -q` without network or API key |
| **Documentation** | README, USAGE_GUIDE, FEATURE_VERIFICATION_GUIDE (Sections A–I) |

## 3-minute demo script

**Option A — Docker (cleanest for judges)**

1. `cd agents/rentrakshak && docker compose build`  
2. `docker compose run --rm test` — 32 passed, no API key  
3. `docker compose run --rm cli` — critical risk + RF-005 on suspicious fixture  
4. `docker compose run --rm seed` — optional demo DB  

**Option B — Local Python**

1. `pytest -q`  
2. `python main.py --listing @tests/fixtures/suspicious_listing.txt`  

Then (optional): `adk web adk_agent` with `GOOGLE_API_KEY`. UI (`streamlit`) is optional and deferred.

Say clearly: rent JSON is **demo-labeled**; community posts are **unverified**; RentRakshak is **not** Google/government.

## Where to look in code

| Topic | Path |
|-------|------|
| Agent instructions | `rentrakshak/agent.py` |
| Red-flag rules | `rentrakshak/services/risk_rules.py` |
| Full report | `rentrakshak/services/safety_report.py` |
| Community | `rentrakshak/services/community.py` |
| Vacating | `rentrakshak/services/vacating.py` |
| Tests | `tests/test_integration.py` |

## Pull request

Submitted to `gdgcblr/open-source-agents` from branch `feat/rentrakshak`.
