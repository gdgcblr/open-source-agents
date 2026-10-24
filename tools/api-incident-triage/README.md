# StackSentry (API Incident Triage)

> Offline-first CLI that redacts common secret patterns locally and suggests cautious first diagnostic checks for common API, PostgreSQL, and network errors.

---

## Overview

### Problem Statement & Intended Users

- **Problem**: Noisy API or database logs are slow to triage by hand, and pasting them into a hosted AI tool can leak credentials.
- **Intended Users**: Developers and junior engineers debugging HTTP/backend failures who want a repeatable, local-first first pass.

### Key Features

- Best-effort local redaction for common authorization headers, secret assignments, and PostgreSQL connection URLs.
- **Multi-signal triage**: detects every matching family, ranks a primary cause, and lists secondary signals.
- **Confidence + severity**: `high` / `medium` / `low` based on exact codes (e.g. `42P01`) vs vague wording.
- **Evidence snippets**: up to three sanitized log lines that triggered matches.
- **Incident card** summary line for demos and handoff.
- **`--json`** structured output for scripts and agent tooling.
- **`--demo`** guided walkthrough using bundled synthetic examples.
- **`compare`** two logs (before/after) to see if the primary incident class changed.
- **`--verbose` / `--quiet`** output modes for mentoring vs quick scans.
- **Risk score + blast radius + playbook** per incident category.
- **`--report`** writes a markdown incident report for handoff.
- **Failure Lab** (`npm run lab`) — tiny local API that breaks on purpose and writes `lab/lab.log`.
- **MCP server** (`npm run mcp`) — expose triage/redact/compare/playbook/report tools to Cursor or other MCP clients (still offline).
- Broader local rule pack: Postgres schema/auth/constraints, DNS, TLS, CORS, timeouts, resource exhaustion, HTTP statuses.
- CLI/lab core uses Node built-ins only; MCP mode needs `npm install` for the official MCP SDK.

---

## Technical Stack

- **Language & Runtime**: JavaScript ES modules on Node.js 20+
- **Agent Framework / Core Library**: Vanilla Node.js (no agent framework)
- **Models**: None (local heuristics only)
- **MCP**: Optional `@modelcontextprotocol/sdk` stdio server
- **External APIs**: None; triage makes no network requests

---

## Architecture & Data Flow

```
file / stdin / MCP tool args
         |
         v
Local secret redaction (redactSecrets)
         |
         v
Multi-signal rule engine (localTriage)
  · all matches → ranked primary + secondary
  · severity / confidence / evidence snippets
  · risk score + blast radius + playbook
         |
    +----+----+------------------+
    |         |                  |
    v         v                  v
  CLI      --report.md      MCP stdio server
 (pretty/JSON)              · open incidents → RAM
                            · close → reports/cases/ (disk)
         ^
Failure Lab (lab/server.mjs) → synthetic boom logs → lab/lab.log
```

Core triage is pure heuristics (no LLM, no network). The lab and MCP server are optional surfaces on the same core.

---

## Prerequisites

- Node.js 20 or newer
- No package manager install step is required for the MVP (built-ins only)
- No API keys or service accounts

---

## Installation & Setup

1. Navigate to the project directory:

```bash
cd tools/api-incident-triage
```

2. For CLI + Failure Lab only, no install is required (Node built-ins).

3. For MCP server support:

```bash
npm install
```

4. Environment variables: none required for triage. See `.env.example`.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `STACKSENTRY_LAB_PORT` | No | `3857` | Port for the optional Failure Lab only |

Triage itself does not require environment variables.

---

## How to Run

```bash
node src/index.mjs examples/sample-error.log
node src/index.mjs examples/connection-refused.log
node src/index.mjs --json examples/sample-error.log
node src/index.mjs --quiet examples/sample-error.log
node src/index.mjs --verbose examples/sample-error.log
node src/index.mjs --report reports/incident.md examples/sample-error.log
npm run demo
node src/index.mjs compare examples/sample-error.log examples/connection-refused.log
```

### Failure Lab (live breakables)

Terminal 1 — start the intentional failure API:

```bash
npm run lab
```

Terminal 2 — hit every boom route, triage `lab/lab.log`, write markdown report:

```bash
npm run lab:boom
```

Or manually:

```bash
curl http://127.0.0.1:3857/boom/schema
node src/index.mjs --report reports/from-lab.md lab/lab.log
```

See [lab/README.md](./lab/README.md) for all `/boom/*` routes.

### MCP server (Cursor / agents)

After `npm install`:

```bash
npm run mcp
```

Register in Cursor MCP settings (see `mcp.example.json`). Use an **absolute** path to `src/mcp-server.mjs`.  
**Restart the MCP server** after pulling changes (stdio process does not hot-reload).

#### Tools (offline)

| Tool | Purpose |
| --- | --- |
| `triage_log` | Redact + triage (+ optional `incident_id`) |
| `redact_secrets` | Local redaction only |
| `compare_logs` | Before/after compare (+ optional incident) |
| `get_playbook` | Playbook / blast radius for a category |
| `make_incident_report` | Markdown incident report |
| `start_incident` / `list_incidents` / `get_incident` | Open cases in **RAM** |
| `add_incident_note` / `close_incident` | Notes; close **archives to disk** and drops RAM |
| `list_saved_cases` / `load_saved_case` | Read closed archive |
| `delete_saved_case` / `clear_saved_cases` / `archive_stats` | Manage disk archive |
| `lab_status` / `lab_start` / `lab_scenarios` / `lab_boom` | Control Failure Lab from the agent |

**Storage model C:** open sessions = RAM only; closed sessions = `reports/cases/<id>.json` + `.md` (gitignored). MCP restart clears RAM but keeps archived files until you delete them.

#### Resources

- `stacksentry://playbooks` and `stacksentry://playbooks/{category}`
- `stacksentry://examples/sample-error.log`
- `stacksentry://examples/connection-refused.log`
- `stacksentry://lab/routes`

#### Prompts

- `junior_oncall_triage` — guided offline triage of a pasted log
- `compare_before_after` — deploy/mitigation compare
- `lab_investigation` — start lab → boom → playbook → close case

#### Example agent flow

1. `start_incident` title="Lab schema boom"  
2. `lab_start` (if needed) → `lab_boom` route=`schema` with `incident_id`  
3. `get_playbook` category=`database-schema`  
4. `close_incident` → markdown case report

Piped input (macOS/Linux):

```bash
cat examples/sample-error.log | node src/index.mjs
```

Windows PowerShell:

```powershell
Get-Content -Raw examples/sample-error.log | node src/index.mjs
```

Help:

```bash
node src/index.mjs --help
```

---

## Example Input & Output

### Example Input (`examples/sample-error.log`)

```text
2026-10-24T08:45:13.112Z ERROR request_id=req_demo_001 method=POST path=/api/users status=500
DatabaseError: relation "users" does not exist
SQLSTATE: 42P01
Authorization: Bearer demo-token-should-be-redacted
DATABASE_URL=postgresql://demo-user:demo-password@localhost:5432/demo_app
```

### Example Output

```text
╔══════════════════════════════════════╗
║           StackSentry                ║
║   Local API incident triage (offline)║
╚══════════════════════════════════════╝

Incident card
─────────────
  [HIGH] database-schema: PostgreSQL may be unable to find a referenced table or relation. Also seen: http-500.

Risk score:  92/100
Severity:    high
Primary:     database-schema
Owner hint:  Backend / data
Confidence:  high (heuristic — verify)
Signals:     2

Likely cause: PostgreSQL may be unable to find a referenced table or relation.
Evidence:     Matched SQLSTATE 42P01 (undefined_table).

Blast radius:
  Reads/writes against missing relations fail; user-facing 5xx likely until migrations align.

Also detected:
  • http-500 (medium confidence, high severity)

Evidence snippets (sanitized):
  | DatabaseError: relation "users" does not exist
  | SQLSTATE: 42P01
  | 2026-10-24T08:45:13.112Z ERROR request_id=req_demo_001 method=POST path=/api/users status=500

Playbook:
  1. Confirm environment and database name (dev vs staging vs prod).
  2. Diff expected schema vs live (migrations, search_path, identifier casing).
  3. Block related deploys until the relation exists or the query is corrected.
  4. Re-run a single synthetic request and confirm the 42P01 signal is gone.

Suggested checks:
  1. Confirm the application is connected to the intended database and environment.
  2. Check the relation name, identifier casing, active schema, and search_path.
  3. Verify that the expected migrations ran successfully in this environment.

Privacy: redaction is local and best-effort.
Note: diagnosis is heuristic, not a proven root cause.
```

The CLI does not dump the raw log. Use `--json` for the full structured payload (`signals`, `secondary`, `evidenceSnippets`, `riskScore`, `playbook`, `summary`).

### Second example (`examples/connection-refused.log`)

```bash
node src/index.mjs examples/connection-refused.log
```

Expected category: `connection-refused` (matched `ECONNREFUSED`). Synthetic secrets in the file are redacted locally before any report is produced.

---

## Supported diagnostic signals

Ranked; all matches are reported, strongest becomes **primary**:

1. PostgreSQL undefined relation/table (`42P01` / wording)
2. PostgreSQL auth failure (`28P01` / wording)
3. PostgreSQL duplicate-key/unique-constraint (`23505` / wording)
4. Connection refused (`ECONNREFUSED`)
5. DNS not found (`ENOTFOUND`)
6. TLS/SSL handshake or certificate errors
7. Timeouts (`ETIMEDOUT` / timed out / vague `timeout`)
8. Resource exhaustion (OOM / connection pool / too many connections)
9. CORS policy blocks
10. HTTP `401`, `403`, `404`, `429`, `500`, `502`, and `503`
11. Unknown / insufficient evidence fallback

---

## How to Test

```bash
npm test
```

Manual smoke checks:

```bash
node src/index.mjs examples/sample-error.log
node src/index.mjs --help
```

Tests use only Node built-ins and require no network access.

---

## Known Limitations

- Diagnosis is heuristic, not a verified root cause. Always confirm against surrounding application, database, and infrastructure evidence.
- Only the listed patterns are recognized; other failures fall back to a generic diagnostic.
- Unknown secret formats may not be redacted. Treat redaction as best-effort, not a DLP product.
- The tool never modifies systems or applies fixes; it only suggests checks.
- Open MCP incident sessions live in process RAM only — restarting the MCP server clears open cases (closed cases remain under `reports/cases/` until deleted).
- Broad “timeout” wording can produce false positives in unrelated log noise.
- Combined Failure Lab logs often pick `database-schema` as primary when many boom routes are mixed; use per-route triage to inspect each class.

---

## Security & Privacy Considerations

- **Secrets Handling**: Common credential patterns are redacted locally before any report is produced. No `.env` is required or loaded for triage.
- **Data Privacy**: Triage transmits nothing. There is no telemetry. Failure Lab binds to localhost only.
- **Safety**: The tool never executes remediation commands, migrations, or shell actions based on the log.
- Do not commit real credentials, customer data, or production logs. Examples and tests use synthetic values only. `reports/` and `lab/lab.log` are gitignored.

---

## Future Improvements

- [ ] Optional, explicitly opt-in hosted-model explanation mode (sanitized payload only; disabled by default)
- [ ] Additional safe diagnostic rules from synthetic fixtures
- [ ] Persist open incident sessions across MCP restarts (opt-in)

---

## License

MIT (see `package.json`). This project is contributed under the repository's open-source license.
