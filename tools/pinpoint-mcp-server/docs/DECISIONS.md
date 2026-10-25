# Decisions — pinpoint-mcp-server

| ID | Decision | Reason |
| :--- | :--- | :--- |
| D-1 | JSON file store instead of SQLite. | No native build on Windows; reduces setup risk for contributors. |
| D-2 | Stdio transport only. | Smallest attack surface; matches how MCP hosts launch servers. |
| D-3 | The agent records turns; the model cannot. | Keeps the record trustworthy and out of model control (see agent docs). |
| D-4 | Injection detection flags, does not block. | Blocking would silently drop user content; flagging preserves it and makes it visible. |
| D-5 | One PR contains the server and the agent. | The agent depends on the server. Happy to split into two PRs (tool first) if maintainers prefer. |
| D-6 | JavaScript (ESM), not TypeScript. | Matches the build time box; logic is ported from ai-pinpoint TypeScript with attribution. |
| D-7 | Contribute docs-first as a Draft PR; code follows in later commits on the same branch. | Lets reviewers see the design early. Ready-for-review only after all checks pass. |
| D-8 | Bookmarking an already-pinned message promotes that pin in place (same `pinId`, new label, `promoted: true`). Pinning an already-pinned message returns it with `alreadyPinned: true`. | A bookmark must carry its label; returning the plain pin would silently drop it (found in the demo). |
| D-9 | Selector and confirm checks run in the handler and return typed codes. SDK-level type errors (for example a negative `ordinal`) are returned by the SDK as `isError` results, not as `{ ok: false }` envelopes. | The SDK validates raw zod shapes before the handler runs. Tests assert `isError`, not a protocol throw. |
| D-10 | `navigate_to_pin` with no matching message returns `ok: true`, `method: not_found`, and keeps the pin. | Not finding a target is a result, not a failure. Pins are never removed by navigation (R6). |
| D-11 | A fuzzy identity repair is persisted inside `store.mutate`. If the write fails, navigation still returns the target and logs a warning. | Navigation should not fail because a repair could not be saved. |
| D-12 | `import_pins` `replace` writes the whole current store to `exports/pre-replace-<timestamp>.json` before replacing. That backup is not size-capped. | A replace must never be the reason user data is lost, even when the store is larger than one import may be. |
| D-13 | Export bundles above the 5 MB import limit are refused with `STORE_FULL`; the message says to export a single session. | Keeps every exported bundle importable. No new error code was added. |
| D-14 | Stored message text is returned only under `untrustedContent`. Labels, notes and tags are returned as plain pin metadata. | Message text is the injection surface; labels and notes are short values the agent itself wrote. Revisit if labels become free-form from untrusted sources. |
| D-15 | The rate limiter (G8) is cut. `PINPOINT_RATE_LIMIT_PER_MIN` is parsed and validated but not enforced. | Time box. Stated in the README and AUDIT so the variable does not look like a control. |
| D-16 | Import merge keeps incoming message ids and pin ids and appends missing ones; messages added to an existing session get the next ordinal. | Pins reference messages by id, so ids must survive a merge. Ordinals are per-session positions and must stay contiguous. |
| D-17 | Agent records every user and assistant turn itself. The model is never offered `record_message` or `start_session`. A model attempt to call them returns `TOOL_NOT_ALLOWED`. | Keeps the record outside model control (D-3). |
| D-18 | Agent overwrites any `sessionId` the model supplies. A model-supplied `confirm` flag is discarded; only the human's yes sets it. | The model cannot pre-approve destructive calls or pick another session. |
| D-19 | Agent destructive gate: `unpin` and `import_pins` with `mode: "replace"` need a y/N answer. `--once` auto-denies. | There is no human at the prompt in `--once` mode. |
| D-20 | Gemini default `MODEL_NAME` is `gemini-2.5-flash` (`agents/pinpoint-agent/src/constants.js`). Not verified against the live API. | The earlier placeholder model name could not be checked from this environment. Gemini mode is not live-tested. |
| D-21 | The agent's Gemini adapter rewrites errors to remove the API key and does not attach the original error as `cause`. | The original error text can contain the key. |
