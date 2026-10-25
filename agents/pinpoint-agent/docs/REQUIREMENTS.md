# Requirements — pinpoint-agent

Status legend: **Done** (built and tested; evidence in [AUDIT.md](AUDIT.md)), **Partial** (part built, gap stated), **Deferred** (not in this release).

## Functional Requirements

| ID | Requirement | Status |
| :--- | :--- | :--- |
| FR-A1 | CLI REPL starts a session and records every human message and final assistant reply through the MCP server. | Done (T-AG-8, T-AG-9b) |
| FR-A2 | "Pin that" / "pin your last answer" calls `pin_message` with `last: "assistant"`. | Done for "pin your last answer" and "pin that" (mock intents, T-AG-1) |
| FR-A3 | A bookmark requires a label; the agent asks for one if missing. | Partial: the mock only bookmarks with `as <label>` present. The agent does not prompt for a missing label. |
| FR-A4 | "What did I pin about X" calls `search_pins`. | Done (T-AG-1, T-AG-8) |
| FR-A5 | "Take me to pin N" lists pins, finds the target, and prints a navigation view with context. | Done (T-AG-8; `▶` marks the target in `view.js`) |
| FR-A6 | Unpin and replace-import ask `Confirm ...? (y/N)` before sending `confirm: true`. | Done for unpin and replace-import (T-AG-6). Interactive prompt is not covered by a test; `--once` auto-denial is. |
| FR-A7 | `--once`, `--session`, `--mock` flags work as specified. | Done (T-AG-1 parseArgs). |
| FR-A7b | `--server` flag. | Deferred. The server path is set with `PINPOINT_SERVER_PATH` instead. |
| FR-A8 | `/pins`, `/help`, `/exit` are handled locally without the model. | Done (`src/index.js`; `/help` and `/exit` are not covered by a test). |
| FR-A8b | `/sessions` command. | Deferred. |

## Non-Functional Requirements

| ID | Requirement | Status |
| :--- | :--- | :--- |
| NFR-A1 | Node.js 20 or newer, cross-platform. | Done on Windows 11 (Node 24.13.1). Linux and macOS not verified. |
| NFR-A2 | Runs fully offline in mock mode (no key, no network). | Done for the model. The mock still starts the local server over stdio. Verified by `npm run demo`. |
| NFR-A3 | Per-model-call timeout of 30 s. | Deferred. The Gemini adapter has no timeout yet. |
| NFR-A4 | Gemini mode latency and cost are not measured. | Not measured. Not claimed. |

## Security Requirements

| ID | Requirement | Maps to | Status |
| :--- | :--- | :--- | :--- |
| SR-A1 | Human input capped at 8,000 chars; control chars stripped; empty input ignored. | G-A1 | Partial: capped (T-AG-4) and empty lines are skipped by the REPL. The agent does not strip control characters itself; the server does so on `record_message`. |
| SR-A2 | Tool allowlist; `record_message`, `start_session` never offered to the model. `delete_session` is not offered because the server does not have it. | G-A2 | Done (T-AG-2) |
| SR-A3 | `sessionId` overwritten by the agent on every call. | G-A3 | Done (T-AG-3) |
| SR-A4 | Tool-call cap per human turn. | G-A4 | Done (T-AG-5) |
| SR-A5 | Destructive calls gated; auto-denied in `--once`. | G-A5 | Done (T-AG-6) |
| SR-A6 | Tool results truncated to 8,000 chars; `untrustedContent` wrapper kept. | G-A6 | Done (`truncateResult` shortens the wrapped text first) |
| SR-A7 | API key from env only; redacted in errors and logs; not passed to the server. | G-A7 | Done for the key in errors (T-AG-7c). The child env is built by `buildChildEnv` but has no test of its own. |
| SR-A8 | No shell execution; no filesystem access beyond `.env`. | G-A8 | Done (no `child_process` in src; `.env` read by `loadDotEnv`) |
| SR-A9 | Model call timeout. | G-A9 | Deferred (same gap as NFR-A3) |
