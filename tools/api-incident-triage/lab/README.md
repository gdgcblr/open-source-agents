# StackSentry Failure Lab

Tiny local HTTP API that **breaks on purpose** and writes synthetic errors to `lab.log`.

No database required. No third-party packages. Synthetic secrets only.

## Quick start

Terminal 1:

```bash
npm run lab
```

Terminal 2:

```bash
npm run lab:boom
```

You should see a **table** where **Category changes per route** (schema → refused → duplicate → …).  
Then StackSentry triages the combined `lab/lab.log` and writes `reports/lab-incident-report.md`.

### Important

- `/boom/schema` **always** returns the same JSON (`42P01`). That is intentional.
- Different routes return different JSON. Try `/boom/refused`, `/boom/timeout`, etc.
- Combined `lab.log` triage often picks `database-schema` as primary because it ranks highest when many signals are present. Use the per-route table from `lab:boom` to see each class.

## Manual hits

```bash
curl http://127.0.0.1:3857/health
curl http://127.0.0.1:3857/scenarios
curl http://127.0.0.1:3857/boom/schema
curl http://127.0.0.1:3857/boom/refused
```

PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:3857/boom/refused
Invoke-RestMethod http://127.0.0.1:3857/boom/timeout
```

Then:

```bash
node src/index.mjs lab/lab.log
node src/index.mjs --report reports/from-lab.md lab/lab.log
```

## Routes

| Route | Simulated failure |
| --- | --- |
| `/boom/schema` | Postgres `42P01` |
| `/boom/refused` | `ECONNREFUSED` |
| `/boom/duplicate` | `23505` |
| `/boom/auth-db` | `28P01` |
| `/boom/timeout` | `ETIMEDOUT` |
| `/boom/dns` | `ENOTFOUND` |
| `/boom/tls` | TLS handshake |
| `/boom/rate-limit` | HTTP 429 |
| `/boom/cors` | CORS block |
| `/boom/pool` | connection slots exhausted |
