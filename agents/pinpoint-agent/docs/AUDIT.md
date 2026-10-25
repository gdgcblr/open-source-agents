# Audit — pinpoint-agent

Status: **functional, Gemini live run not tested.** Every check below was run on this environment. Anything not built or not run is marked.

Environment (recorded 24 Oct 2026): Windows 11 Pro 10.0.26200 (build 26200.9711), Node v24.13.1, npm 11.8.0. Dependencies installed with a clean `npm ci` from `package-lock.json`.

## 1. Traceability Matrix

Status key: **PASS** = test IDs exist and pass. **PARTIAL** / **DEFERRED** = see the requirement notes in [REQUIREMENTS.md](REQUIREMENTS.md).

| Requirement | Test ID(s) | Status |
| :--- | :--- | :--- |
| FR-A1 record every turn through the server | T-AG-8, T-AG-9b | PASS |
| FR-A2 pin your last answer → `pin_message` `last: assistant` | T-AG-1, T-AG-8 | PASS |
| FR-A3 bookmark needs a label; agent prompts if missing | — | PARTIAL: label required by the server; no label prompt |
| FR-A4 what did I pin about X → `search_pins` | T-AG-1, T-AG-8 | PASS |
| FR-A5 take me to pin N → list then navigate, with context | T-AG-1b, T-AG-8 | PASS |
| FR-A6 destructive calls ask y/N | T-AG-6 (auto-deny, approve, model confirm ignored) | PASS (interactive prompt itself not tested) |
| FR-A7 `--once`, `--session`, `--mock` | T-AG-1 (parseArgs), manual `--once` run (§4) | PASS |
| FR-A7b `--server` flag | — | DEFERRED |
| FR-A8 `/pins`, `/help`, `/exit` local | manual (REPL not automated) | PARTIAL: `/pins` runs `listPins`; REPL not under test |
| FR-A8b `/sessions` | — | DEFERRED |
| SR-A1 input cap 8,000; control chars; empty ignored | T-AG-4 | PARTIAL: control chars stripped by the server, not the agent |
| SR-A2 allowlist; record/start never offered | T-AG-2 | PASS |
| SR-A3 sessionId forced | T-AG-3 | PASS |
| SR-A4 tool-call cap | T-AG-5 | PASS |
| SR-A5 destructive gate; auto-denied in `--once` | T-AG-6 | PASS |
| SR-A6 result truncation keeps untrustedContent | (truncateResult in guardrails; no dedicated test) | PARTIAL: exercised by the flow, no unit test of the truncation branch |
| SR-A7 key from env only; redacted in errors | T-AG-7c, `redactSecret` test in `config.test.js` | PASS |
| SR-A8 no shell, no file access beyond `.env` | source review; no `child_process` in `src/` | PASS (review) |
| SR-A9 model call timeout | — | DEFERRED |
| NFR-A2 offline in mock mode | T-AG-8 (real server), `npm run demo` | PASS |
| Injection text recorded as data, no unpin | T-AG-9, T-AG-9b | PASS |
| Gemini adapter: functionDeclarations, tool calls, key never in errors | T-AG-7, T-AG-7b, T-AG-7c | PASS with a **fake client only**. Live API not called. |
| Default server path resolves | T-AG-10 | PASS (this test caught a real bug, see §5) |

Tests (19): T-AG-1, T-AG-1b, T-AG-1c, parseArgs, T-AG-2, T-AG-3, T-AG-4, T-AG-5, T-AG-6, T-AG-7, T-AG-7b, T-AG-7c, T-AG-8, T-AG-8b, T-AG-9, T-AG-9b, T-AG-10, T-AG-10b, redactSecret.

## 2. Check Results

| Check | Command | Result |
| :--- | :--- | :--- |
| Lint | `npm run lint` | PASS: 0 problems, `--max-warnings 0` |
| Tests + coverage | `npm run test:coverage` | PASS: 20/20. All files: line 75.66%, branch 63.54%, function 68.42% |
| Secret scan | `npm run scan:secrets` | PASS: `scan:secrets OK` |
| Dependency audit | `npm audit --omit=dev --audit-level=high` | PASS: `found 0 vulnerabilities` |
| Demo | `npm run demo` | PASS: `demo OK` (transcript in README) |
| Clean install | `rm -rf node_modules && npm ci && npm run verify` | PASS: exit 0 |

Coverage is below the server's 93.88% and below the 80% target used for the server. No coverage gate is enforced on the agent. The uncovered code is mainly the interactive REPL loop in `src/index.js` and the live Gemini call path.

## 3. Known gaps

- **Gemini live run: not tested.** The adapter has only been run against a fake client. No transcript from the real API exists. Tool-call behaviour with the real model is unknown.
- Model default `gemini-2.5-flash` is not checked against the live API (D-20 in the server DECISIONS).
- Deferred: `--server` flag, `/sessions`, bookmark label prompt, model call timeout (NFR-A3 / SR-A9).
- Mock intents are regex-based and cover a fixed set of phrasings.
- The interactive `y/N` prompt and the REPL loop are not automated; `--once` and the demo cover the code paths around them.

## 4. Manual run recorded

`node src/index.js --mock --once "pin your last answer"` on an empty session, with `PINPOINT_DATA_DIR` set to a temporary directory. Output (stdout), exit 0:

```
Tool error: NOT_FOUND (no assistant message in this session).
```

## 5. Defect found and fixed during this audit

`src/config.js` resolved the default server path from `src/` instead of the package root, so the spawned server did not exist. `--once` failed with `MCP error -32000: Connection closed`. The demo and tests passed an explicit path, so they did not catch it. Fixed, and T-AG-10 now asserts that the default path exists.
