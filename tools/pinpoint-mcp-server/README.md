# Pinpoint MCP Server

> A local-only MCP server that lets AI agents pin, bookmark, search and navigate back to specific messages in long agent-human conversations. Zero network calls.

> **Status: functional.** 13 tools, stdio transport, export/import, guardrails and audit are built and tested on Windows. The rate limiter and ai-pinpoint bundle import are deferred (see Known Limitations). Test evidence: [docs/AUDIT.md](docs/AUDIT.md).

Adapted from [TeamAnoryx/ai-pinpoint](https://github.com/TeamAnoryx/ai-pinpoint) (MIT © 2026 Anoryx Tech Solutions).

---

## Overview

### Problem Statement & Intended Users
- **Problem**: In long agent sessions the messages that matter get buried. There is no standard way for an agent to bookmark a message and return to it later with its surrounding context.
- **Intended Users**: Developers building agents, and anyone using an MCP client (Claude Desktop, Claude Code, or any other MCP host).

### Key Features
- Record conversation turns, then pin or bookmark any message by `messageId`, `ordinal`, `last` (user / assistant / any) or `textQuery`.
- List, search (keyword + trigram), and navigate to a pin with a context window and a position such as `message 2 of 9`.
- Update label, note and tags; unpin only with `confirm: true`.
- Export and import pins as a native JSON bundle. Import merges by default; `replace` needs `confirm: true` and backs up the current store first.
- Secret redaction before storage, prompt-injection flagging (flag, not block), stored text returned only under `untrustedContent`, path-confined transfer, and an audit log that stores argument hashes only.

### Implementation Status

| Item | Status |
| :--- | :--- |
| Project scaffold, eslint config, .gitignore, .env.example | Done |
| Config, constants, logger, ids | Done |
| Text primitives (hash, normalise, trigram, clamp) | Done |
| Schema validators, JSON store (mutex, atomic write, quarantine) | Done |
| Store lock-timeout ordering (T-STO-8) | Done |
| Identity resolution (id → hash → fuzzy → not_found) and search | Done |
| Guardrails: redaction, injection flag, control chars, path safety, untrusted wrapper | Done |
| Audit log (argument hashes only) | Done |
| 13 MCP tools: start_session, record_message, pin_message, bookmark_message, list_pins, search_pins, navigate_to_pin, update_pin, unpin, list_sessions, export_pins, import_pins, health | Done |
| Entry point `src/index.js` (stdio, SIGINT/SIGTERM) and `src/server.js` | Done |
| Native export / import (`src/transfer.js`) | Done |
| Offline verifier, secret scanner, stdio smoke test | Done |
| `update_pin` reorder (up / down / top / bottom) | Deferred |
| `delete_session` tool | Deferred |
| ai-pinpoint bundle import (snippet-only navigation) | Deferred |
| Rate limiter (SR-8). `PINPOINT_RATE_LIMIT_PER_MIN` is parsed but **not enforced** | Deferred |
| Coverage threshold as a gate (numbers are reported, not enforced) | Deferred |

---

## Technical Stack

- **Language & Runtime**: JavaScript (ES modules), Node.js 20+
- **Core Library**: Model Context Protocol SDK `@modelcontextprotocol/sdk` (stdio transport). Lockfile version: see `package-lock.json`.
- **Tool input schemas**: `zod` 4.x (the SDK's raw-shape schemas)
- **Storage**: JSON file with atomic rename. No native modules.
- **Tests**: built-in `node:test` and `node:assert/strict`, real MCP client over the SDK in-memory transport and over real stdio
- **Lint**: ESLint 10 with `@eslint/js` and `globals`
- **Models**: none. This server does not call any model.
- **External APIs**: none.

---

## Architecture & Data Flow

```
MCP client (Claude Desktop / Claude Code / agent)
        │  stdio (JSON-RPC, stdout = protocol, logs = stderr)
        ▼
src/index.js  ──▶  src/server.js  (McpServer, 13 tools in 4 groups)
                        │
                        ├─▶ tools/session-tools.js   start_session, record_message, list_sessions
                        ├─▶ tools/pin-tools.js       pin_message, bookmark_message, update_pin, unpin
                        ├─▶ tools/query-tools.js     list_pins, search_pins, navigate_to_pin, health
                        ├─▶ tools/transfer-tools.js  export_pins, import_pins
                        │
                        ├─▶ guardrails.js  (redaction, injection flag, path safety, untrusted wrapper)
                        ├─▶ schema.js      (hand validators at the storage boundary)
                        ├─▶ identity.js    (id → hash → fuzzy → not_found; selector rules)
                        ├─▶ search.js      (keyword + trigram ranking)
                        ├─▶ transfer.js    (bundle parse / build, DATA_DIR/imports and exports only)
                        ├─▶ store.js  ──▶  store.json   (lock, tmp write, rename)
                        │                  quarantine.json, store.corrupt-*.json
                        └─▶ audit.js  ──▶  audit.jsonl  (argument hash only, never text)
```

Every tool call goes through one wrapper. Expected errors return `{ isError: true }` with `{ ok: false, error: { code, message } }`. Unexpected errors return `INTERNAL` with a correlation id; details go to stderr only.

---

## Prerequisites

- Node.js 20 or newer. This build was run on Node 24.13.1 (see Testing & Verification below).
- npm (ships with Node). This build was run on npm 11.8.0.
- Windows, macOS or Linux. Windows is the verified platform so far.

---

## Installation & Setup

PowerShell:
```powershell
cd tools\pinpoint-mcp-server
npm ci
Copy-Item .env.example .env   # optional; every variable has a default
```

bash:
```bash
cd tools/pinpoint-mcp-server
npm ci
cp .env.example .env          # optional
```

`npm ci` installs from `package-lock.json` and needs no native build tools.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `PINPOINT_DATA_DIR` | No | `<server folder>/.data` | Directory for `store.json`, `quarantine.json`, `audit.jsonl`, `exports/`, `imports/`. Must not be a filesystem root. |
| `PINPOINT_LOG_LEVEL` | No | `info` | `debug` / `info` / `warn` / `error`. Logs go to stderr only. |
| `PINPOINT_AUDIT` | No | `on` | `on` / `off`. Audit log of tool calls (argument hash only). |
| `PINPOINT_REDACT` | No | `on` | `on` / `off`. Secret redaction before storage. |
| `PINPOINT_RATE_LIMIT_PER_MIN` | No | `120` | Parsed and validated, **not enforced** (deferred, see Known Limitations). |

---

## How to Run

```bash
npm start
```

The server waits silently on stdin. That is correct for stdio MCP: a host launches it and speaks JSON-RPC on stdin/stdout. Startup logs go to stderr, for example `{"level":"info","message":"pinpoint-mcp-server ready",...}`.

MCP client config example (Claude Desktop: `%APPDATA%\Claude\claude_desktop_config.json` on Windows). Replace the placeholder with the absolute path to this repository:

```json
{
  "mcpServers": {
    "pinpoint": {
      "command": "node",
      "args": ["<ABSOLUTE_PATH_TO>/tools/pinpoint-mcp-server/src/index.js"]
    }
  }
}
```

Other hosts follow the same shape: `command` is `node` and `args` points at `src/index.js`.

---

## Example Input & Output

Real output of `npm run smoke` on this environment (trimmed to the transcript; ids differ on every run). The smoke test starts `src/index.js` over stdio with a temporary data directory and calls all 13 tools:

```
PASS  start_session  {"title":"smoke"}  ->  sessionId
PASS  record_message  {"sessionId":"s_mvmnbboc_e1wwp0","role":"user","text":"Explain JWT refresh token  ->  messageId,ordinal,redacted,redactionTypes,suspicious,truncated
PASS  record_message  {"sessionId":"s_mvmnbboc_e1wwp0","role":"assistant","text":"Refresh tokens rotat  ->  messageId,ordinal,redacted,redactionTypes,suspicious,truncated
PASS  record_message  {"sessionId":"s_mvmnbboc_e1wwp0","role":"assistant","text":"Keep the old token f  ->  messageId,ordinal,redacted,redactionTypes,suspicious,truncated
PASS  pin_message  {"sessionId":"s_mvmnbboc_e1wwp0","last":"assistant","label":"rotation"}  ->  pin,alreadyPinned,promoted
PASS  bookmark_message  {"sessionId":"s_mvmnbboc_e1wwp0","ordinal":0,"label":"jwt-basics"}  ->  pin,alreadyPinned,promoted
PASS  list_pins  {"sessionId":"s_mvmnbboc_e1wwp0"}  ->  pins,count,returned
PASS  search_pins  {"sessionId":"s_mvmnbboc_e1wwp0","query":"rotation"}  ->  matches,count
PASS  navigate_to_pin  {"pin":"p_mvmnbbpg_c50ks5","contextBefore":1,"contextAfter":1}  ->  pin,method,position,target,context
PASS  update_pin  {"pinId":"p_mvmnbbpg_c50ks5","label":"refresh-rotation","tags":["auth"]}  ->  pin
PASS  export_pins  {"sessionId":"s_mvmnbboc_e1wwp0","fileName":"smoke-export"}  ->  path,bytes,counts
PASS  import_pins  {"fileName":"smoke-export","mode":"merge"}  ->  mode,sessionsAdded,sessionsMerged,messagesAdded,pinsAdded,quarantined,backup
PASS  unpin  {"pinId":"p_mvmnbbpg_c50ks5","confirm":true}  ->  pinId,removed
PASS  list_sessions  {}  ->  sessions,count
PASS  health  {}  ->  counts,lastCorruptionEvent,quarantined,redaction,audit,limits
smoke OK: 13/13 tools, all replies ok
```

Stored message text is never returned bare: it sits under `untrustedContent` with a data notice. Failures use the `{ ok: false, error: { code, message } }` envelope described in the Architecture section.

---

## How to Test

```bash
npm test                 # 51 tests (node:test)
npm run test:coverage    # same tests with line / branch / function coverage
npm run verify:offline   # static: no network/process APIs or console.log in src/
npm run scan:secrets     # key-shaped secrets, masked output
npm run audit:deps       # npm audit --omit=dev --audit-level=high (needs registry access)
npm run smoke            # stdio end-to-end, all 13 tools
npm run verify           # all of the above, with lint first
```

Last recorded run (clean `npm ci`, Windows): `npm run verify` exit 0. Details, per-check results and test IDs are in [docs/AUDIT.md](docs/AUDIT.md).

---

## Known Limitations

- **Deferred features**: `update_pin` reorder, `delete_session`, ai-pinpoint bundle import, the rate limiter (SR-8; the env variable is parsed but not enforced), and a coverage threshold gate.
- **Single-process writer.** Two server processes on the same data directory can race. A lock serialises writes inside one process only.
- **JSON store** is not suited to very large histories. `MAX_STORE_BYTES` is 50 MB; exports above the 5 MB import limit are refused (`STORE_FULL`) and should be made per session.
- **Redaction is pattern-based.** It can miss secrets. The Aadhaar-shaped pattern (12 digits in groups of 4) also matches other 12-digit numbers, so it over-redacts.
- **Injection detection is heuristic.** It flags phrases such as "ignore all previous instructions". It can flag harmless text that contains those words, and it does not block.
- **Identity repair** uses trigram similarity on the stored snippet. A heavily edited message may come back as `not_found`; the pin is kept.
- **No encryption at rest.** The data directory is protected only by OS file permissions.
- **Replace import** discards the current store after `confirm: true`. The previous store is written to `exports/pre-replace-<timestamp>.json` first; nothing else is kept.
- **Platform**: only Windows 11 has been tested. macOS and Linux are expected to work but are not verified.

---

## Security & Privacy Considerations

- **Secrets Handling**: No secrets are needed. The server reads only its own environment variables.
- **Data Privacy**: The server makes zero network calls. Stored conversation text stays in `PINPOINT_DATA_DIR` on local disk.
- **Safety**: The server runs no shell commands and spawns no child processes. Destructive tools (`unpin`, `import_pins` with `mode: "replace"`) require `confirm: true`. Imports are read only from `DATA_DIR/imports` and exports are written only to `DATA_DIR/exports`; traversal and symlinks are refused (`PATH_REJECTED`).
- **Audit**: each tool call appends a line with a hash of its arguments, never the arguments, labels, notes or message text.
- Full threat model: [docs/SECURITY.md](docs/SECURITY.md).

---

## Testing & Verification Notes

| Item | Value (recorded in this environment) |
| :--- | :--- |
| OS | Windows 11 Pro, 10.0.26200 (build 26200.9711) |
| Node | v24.13.1 |
| npm | 11.8.0 |
| Clean install | `npm ci` from `package-lock.json` (exit 0) |
| `npm run verify` | exit 0: lint, 51/51 tests, offline OK, secret scan OK, audit 0 vulnerabilities, smoke 13/13 |

---

## Future Improvements

- [ ] Deferred items listed above.
- [ ] SQLite or FTS backend (needs a native-build decision on Windows).
- [ ] Encryption at rest.
- [ ] MCP resources for pins.
- [ ] Streamable HTTP transport with authentication.

---

## License

MIT, per the repository license. Code adapted from ai-pinpoint keeps Anoryx's MIT notice (see the credit line above and file headers).
