## Project Overview

- **Project Name:** Meeting Assistant Flow
- **Category:** `agents/meeting-assistant-flow`
- **Frameworks & Technologies Used:** Python, Flask, Google ADK, Gemini, MCP, Google Calendar API, OAuth/OpenID Connect, SQLite, OS keychain.

### Description

Adds a conversational meeting assistant that answers availability questions, finds shared slots, and prepares meeting descriptions and agendas. Gemini calls a read-only ADK scheduling function; the function queries Google Calendar free/busy and invokes the local MCP `find_slots` tool. The backend validates the tool result and requires an exact invitation preview, explicit approval, and an availability recheck before event creation.

Attendee names require supplied email addresses; email addresses are replaced with placeholders in model context. Secondary-calendar mappings support shared calendars whose IDs differ from attendee emails. Inaccessible calendars are marked unknown, never assumed free. Refreshing starts a new chat while preserving account login and Calendar consent; unresolved creation operations remain recoverable.

## Contribution Checklist

- [x] **Directory & Naming:** Only `agents/meeting-assistant-flow/` is changed.
- [x] **Documentation:** README follows the repository template and documents setup, tools, usage, guardrails, and limitations.
- [x] **Reproducible Setup:** Dependencies installed in a clean Python 3.12 environment; `pip check` passed.
- [ ] **Core Functionality Tested:** 103 tests pass; live Google login and shared-secondary-calendar free/busy work. Live Gemini returned timeouts/504; real invitation delivery and write-consent still need manual verification.
- [x] **Example Usage:** README distinguishes synthetic tests from live results.
- [x] **Dependencies Declared:** Runtime and development manifests are included.
- [x] **Secrets & Security:** `.env.example` has blank/placeholders only. Credentials, `.env`, and the local database are ignored and excluded from the commit.
- [x] **Scope Limitation:** No unrelated repository files are changed.

## Testing & Verification Notes

- `python -m pytest -q`: **103 passed**, including in the clean PR checkout.
- Real MCP stdio subprocess; real ADK runner with an offline model issuing a scheduling function call.
- Tests cover OAuth validation, account isolation, CSRF, secret blocking, missing-detail clarification, calendar mappings, busy-time exclusion, unknown access, preview approval, conflict rechecks, duplicate prevention, uncertain-operation recovery, and chat reset.
- Browser checks verified the single-window UI and that reload clears prior chat details.
- Live Google Calendar free/busy succeeded using a shared secondary Calendar ID.
- Live Gemini timed out/returned HTTP 504. Automated tests do not send invitations; real delivery remains unverified.
