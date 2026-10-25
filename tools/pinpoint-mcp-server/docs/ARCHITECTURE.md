# Architecture — pinpoint-mcp-server

Status: design. Modules marked *planned* are not written yet.

## Module Map

| Module | Responsibility |
| :--- | :--- |
| `src/index.js` | Entry. Load config, create store, `createServer`, connect stdio. Handles SIGINT/SIGTERM. |
| `src/server.js` | `createServer({ store, audit, config, clock })` returns an `McpServer` with all 13 tools registered. |
| `src/constants.js` | Every limit and threshold (R8). |
| `src/logger.js` | stderr-only logger. |
| `src/config.js` | Env to validated config. Rejects filesystem-root data dirs. |
| `src/ids.js` | `<prefix>_<base36 ms>_<6 random>` ids. |
| `src/text.js` | FNV-1a, normalise, trigram similarity, clamp. Adapted from ai-pinpoint. |
| `src/schema.js` | Hand validators that never throw. Return `{ ok, value } \| { ok: false, error }`. |
| `src/store.js` | JSON store. In-process mutex, clone, validate, tmp write, rename. Quarantine. |
| `src/identity.js` | Message resolution: id → hash → fuzzy → not_found. Selector resolution. |
| `src/search.js` | Keyword and trigram ranking. |
| `src/guardrails.js` | Redaction, injection flag, path safety. Rate limit (G8) cut from this release. |
| `src/audit.js` | Append-only JSONL audit, args hash only. |
| `src/transfer.js` | Export and import, including ai-pinpoint bundle mapping. |
| `src/tools/*.js` | Tool groups: session, pin, query, transfer. Each exports `register(server, deps)`. |

## Data Flow per Tool Call

1. Rate-limit check (`guardrails.js`).
2. Zod validation of the raw input shape (SDK level).
3. Handler-level checks (exactly-one selector, confirm flags, path safety).
4. Store operation through `store.mutate(fn)` or read-only access.
5. Output: stored text wrapped under `untrustedContent`.
6. Audit line appended (failure does not fail the call).
7. Any unexpected error becomes `INTERNAL` with a correlation id.

## Identity Chain

```
pin.messageId  ── exact match ──────────────▶ method: id
      │ miss
pin.targetHash ── exact (nearest ordinal) ──▶ method: hash
      │ miss
trigram(snippet vs message prefixes) ≥ 0.6 ─▶ method: fuzzy   (repairs targetHash/messageId, repairCount++)
      │ miss
                                             method: not_found  (pin kept, R6)
```

## Store Write Path

lock (in-process mutex, 5 s timeout) → clone current state → apply `fn` → validate result → write `store.json.tmp` → `fs.renameSync` to `store.json`. On any error the previous file is untouched and a typed error is returned.

Load: missing file → empty store. Unparseable JSON → renamed to `store.corrupt-<timestamp>.json`, empty store, `health` reports it. Valid JSON with invalid records → bad records to `quarantine.json` with the validation error; good records kept.

## Error Codes

`INVALID_INPUT`, `INVALID_SELECTOR`, `AMBIGUOUS`, `NOT_FOUND`, `LIMIT_SESSIONS`, `LIMIT_MESSAGES`, `LIMIT_PINS`, `STORE_FULL`, `RATE_LIMITED`, `CONFIRMATION_REQUIRED`, `PATH_REJECTED`, `IMPORT_INVALID`, `LOCK_TIMEOUT`, `INTERNAL`.

## Ported from ai-pinpoint vs new

| Ported (adapted, attributed) | New |
| :--- | :--- |
| FNV-1a 32-bit, `normaliseForHash`, trigram Jaccard with early exit, surrogate-safe clamp, validator style | MCP tool surface, JSON file store, single-writer lock, pin/bookmark split, navigation context window, ai-pinpoint bundle mapping, audit log, path and redaction guardrails |
