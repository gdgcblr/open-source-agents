# Audit — pinpoint-mcp-server

Status: **functional.** All checks below were run on this environment. Anything not built or not run is marked as such.

Environment (recorded 24 Oct 2026): Windows 11 Pro 10.0.26200 (build 26200.9711), Node v24.13.1, npm 11.8.0. Dependency versions are the ones in `package-lock.json`, installed with a clean `npm ci`.

## 1. Traceability Matrix

Status key: **PASS** = test IDs exist and pass. **DEFERRED** = intentionally not built in this release (see §3).

| Requirement | Guardrail | Test ID(s) | Status |
| :--- | :--- | :--- | :--- |
| FR-1 record turns | G1, G2 | T-TOOL-2 | PASS |
| FR-2 pin by selector (exactly one) | G1 | T-ID-5, T-TOOL-2, T-TOOL-3 | PASS |
| FR-3 bookmark needs label | G1 | T-TOOL-3, T-TOOL-5b | PASS |
| FR-4 list pins (session / kind / tag / limit) | — | T-TOOL-2 | PASS |
| FR-5 search ranking | — | T-SRCH-1, T-TOOL-2 | PASS |
| FR-6 navigate with position and context (0–10) | — | T-ID-1..4, T-TOOL-2 | PASS |
| FR-7 update label / note / tags | G1 | T-TOOL-2 | PASS |
| FR-7 update reorder (up / down / top / bottom) | — | — | DEFERRED |
| FR-8 unpin only with confirm | G7 | T-TOOL-2, T-TOOL-3 | PASS |
| FR-9 native export / import | G6, G12 | T-TRF-1, T-TRF-3 | PASS |
| FR-9 ai-pinpoint bundle import | — | — (`T-TRF-2` not written) | DEFERRED |
| FR-10 health (no message text) | — | T-TOOL-1, T-TOOL-2 | PASS |
| FR-11 idempotent pin | — | T-TOOL-5 | PASS |
| SR-1 validation at tool and storage boundary | G1 | T-SCH-1, T-TOOL-3, T-TOOL-3b | PASS |
| SR-2 clamps and control characters | G2 | T-TXT-4, T-GR-2, T-SCH-1 | PASS |
| SR-3 capacity limits return typed errors | G3 | T-STO-5 | PASS |
| SR-4 secrets redacted before storage | G4 | T-GR-1, T-TOOL-4 | PASS |
| SR-5 injection phrases flagged, not blocked | G5 | T-GR-2, T-TOOL-4 | PASS |
| SR-6 import/export confined; symlinks refused | G6 | T-GR-3, T-TOOL-3 (`PATH_REJECTED`) | PASS |
| SR-7 destructive tools need confirm | G7 | T-TRF-4, T-TOOL-2, T-TOOL-3 | PASS |
| SR-8 rate limit | G8 | — (`T-GR-4` not written) | DEFERRED |
| SR-9 no forbidden network / process APIs in src | G9 | T-OFF-1, T-OFF-2 | PASS |
| SR-10 stdout hygiene (no console.log in src) | G10 | T-OFF-1, T-OFF-2 | PASS |
| SR-11 unexpected errors → INTERNAL + correlation id | G11 | T-TOOL-3 (envelope shape for expected errors) | PARTIAL: no test forces an unexpected throw into `wrapTool`, so the INTERNAL path is untested |
| SR-12 corrupt / invalid records quarantined, never deleted | G12 | T-STO-3, T-STO-4, T-TRF-3 | PASS |
| SR-13 audit excludes text and labels | §6.8 | T-AUD-1, T-TOOL-4 | PASS |
| Lock ordering after LOCK_TIMEOUT (G1 fix) | — | T-STO-8 | PASS |

Other passing unit tests: T-ID-1..4, T-STO-1, T-STO-2, T-STO-6, T-STO-7, T-TXT-1..3, T-GR-5, T-AUD-2, T-SRCH-1 (second case), T-OFF-1b, T-TOOL-5b, and the read-failure and data-dir tests in `store.test.js` and `config.test.js`.

## 2. Check Results

| Check | Command | Result |
| :--- | :--- | :--- |
| S1 Lint | `npm run lint` | PASS: "ESLint: No issues found" (`--max-warnings 0`) |
| S2 Tests + coverage | `npm run test:coverage` | PASS: 51/51 tests. All files: line 93.88%, branch 80.64%, function 93.48% |
| S3 Offline | `npm run verify:offline` | PASS: `verify:offline OK (…\src)` |
| S4 Secret scan | `npm run scan:secrets` | PASS: `scan:secrets OK` (fake keys are built at runtime; none are literals) |
| S5 Dependency audit | `npm audit --omit=dev --audit-level=high` | PASS: `found 0 vulnerabilities` |
| S6 Tracked-file hygiene | `git ls-files` for node_modules, .env, .data, .jsonl, store json | PASS: no matches (§4) |
| S7 Scope | `git diff --name-only upstream/main...HEAD` | PASS: every changed path is inside `tools/pinpoint-mcp-server/`, `agents/pinpoint-agent/`, `tools/README.md` or `agents/README.md` (§4) |
| S8 Smoke over stdio | `npm run smoke` | PASS: `smoke OK: 13/13 tools, all replies ok` |
| S9 Agent demo | `npm run demo` in the agent folder | PASS: `demo OK` (see the agent AUDIT) |
| Clean install | `rm -rf node_modules && npm ci && npm run verify` | PASS: exit 0; 51/51; same numbers as above |

## 3. Known gaps and deferred items

Built and tested: config, constants, logger, ids, text primitives, schema validators, JSON store (lock, atomic write, quarantine, lock-timeout ordering), identity resolution, search, guardrails, audit log, the 13 MCP tools, server factory, stdio entry, native export/import, offline verifier, secret scanner, smoke test.

Deferred (recorded in the README and REQUIREMENTS):
- `update_pin` reorder (up / down / top / bottom). Label, note and tags only.
- `delete_session` tool. Not part of the 13.
- ai-pinpoint bundle import (`T-TRF-2` was never written).
- Rate limiter (SR-8, `T-GR-4`). `PINPOINT_RATE_LIMIT_PER_MIN` is parsed but not enforced. The DoS row in SECURITY.md is only partly covered by size and capacity limits.
- Coverage threshold as a gate. Numbers are reported above only.
- Gemini live run (agent side; see the agent AUDIT).

Tool count: 13. The keep list is `start_session`, `record_message`, `pin_message`, `bookmark_message`, `list_pins`, `search_pins`, `navigate_to_pin`, `update_pin`, `unpin`, `list_sessions`, `export_pins`, `import_pins`, `health`.

## 4. Final-check output

Run after the last code change (commit `561c9f9` and the docs commit that followed).

- `git ls-files | grep -iE "node_modules|(^|/)\.env$|\.data/|\.jsonl$|store[^/]*\.json$"`: no output.
- `git diff --name-only upstream/main...HEAD`: 78 paths, all inside the allowed folders or the two index READMEs.
- Key-pattern grep over both folders (`sk-`, `AIza`, `AKIA`, `gh[pousr]_`, `xox`, private-key header): no output.
- Working tree clean after push.
