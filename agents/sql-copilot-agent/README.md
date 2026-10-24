# SQL Copilot Agent

> Talk to your database in plain English — no forms. An autonomous agent inspects the schema, writes the SQL to **answer questions** or **create/update records**, self-corrects on errors, and only writes behind guardrails (confirmation, atomic transactions, no hard deletes, no schema changes).

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Getting data in and out of a database is a constant bottleneck. Non-technical users wait on an engineer to run a query or add a record, and even engineers lose time because the *first* query is usually wrong — a mistyped column, a bad join, an empty result. The hard part isn't generating SQL once; it's the correction loop that follows. And letting an LLM write to a database is risky without hard guardrails.
- **Intended Users**: Developers, analysts, PMs, and support teams who need to read from *and* safely update a database without hand-writing (and debugging) SQL.

### Is this an agent or a tool?
**This is an agent**, built on the **Google Agent Development Kit (ADK)**. It runs an autonomous reasoning loop — it *plans*, chooses which tool to call, reads the result, and **retries with corrected SQL when something fails**. The three functions it calls (`inspect_schema`, `run_query`, `execute_transaction`) are the *tools* it uses; the agent is the ADK-driven loop that orchestrates them. This is what separates it from a one-shot "text-to-SQL" prompt.

### Key Features
- **Plain English in, no forms**: describe what you want ("add an order for Aarav: 2 keyboards") and the agent resolves the IDs and writes the rows itself.
- **Read and write**: answers questions (`run_query`) and creates/updates records (`execute_transaction`).
- **Self-correcting loop**: when a query errors or returns nothing useful, the error is fed back to the model, which rewrites the SQL and tries again.
- **Schema-grounded**: the agent always inspects the live schema first, so it never hallucinates column names.
- **Guardrails on every write** (enforced in code, not left to the model):
  - **Confirmation gate** — the exact SQL is shown and must be approved before anything commits.
  - **Atomic transactions** — multiple statements commit together or not at all; any error rolls the whole batch back.
  - **No hard deletes** — `DELETE` is blocked; records are removed via **soft delete** (`UPDATE ... SET is_deleted = 1`).
  - **No schema changes** — `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, etc. are blocked, so no table or database can ever be dropped.
- **Transparent trace**: every step (`→ tool call` / `← result`) is printed, so you can watch the agent reason, write, and recover.
- **Zero setup data**: ships with a seeded SQLite demo database; works out-of-the-box with just an API key.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: Google Agent Development Kit (`google-adk`) — ADK `Agent` + `InMemoryRunner` drive the tool-use loop; tools are registered as plain Python functions
- **Models**: Gemini 3.8 Flash (configurable via `MODEL_NAME`)
- **Database access**: SQLAlchemy — the agent connects via a `DATABASE_URL`, defaulting to a bundled SQLite demo but able to target any SQLite / PostgreSQL / MySQL database
- **Tools**: three agent tools — `inspect_schema`, `run_query` (read), `execute_transaction` (guarded write)

---

## Architecture & Data Flow

```
[NL instruction] --> [SqlCopilotAgent loop] --> [Gemini 3.8 Flash]
                           |                         |
                           |  (1) inspect_schema ----+
                           |  (2) run_query(sql) -----+   (read / resolve ids)
                           |  (3) execute_transaction-+   (guarded write)
                           |        |
      read path  <---------+        +--> ok?     --> plain-English answer + SQL
                           |        +--> error?  --> feed error back, retry (self-correct)
                           |
      write path -> validate (no DELETE / no DDL) -> CONFIRM -> transaction
                           |                                        |
                           |                            commit all  OR  rollback all
                           v
                 [SQLAlchemy engine -> DATABASE_URL]   (SQLite demo | your Postgres/MySQL/SQLite)
```

ADK runs the loop until the model stops requesting tools and returns a final answer. Reads run on a connection that is never committed (so a read can't persist anything); writes go through `execute_transaction`, which validates, confirms, and commits atomically (or rolls back). The database is chosen by `DATABASE_URL` — see [Using Your Own Database](#using-your-own-database).

The demo data is seeded automatically by `database.py` (no setup needed). [`schema.sql`](schema.sql) documents the same schema + seed data for reference, and can rebuild the demo by hand: `sqlite3 demo.db < schema.sql`.

---

## Prerequisites

- Python 3.10+
- `pip`
- A free Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/sql-copilot-agent
   ```

2. **Set up the virtual environment and install dependencies:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # then edit .env and set GEMINI_API_KEY
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes | *None* | Gemini / Google AI Studio API key (`GOOGLE_API_KEY` also accepted) |
| `MODEL_NAME` | No | `gemini-3.8-flash` | Gemini model identifier |
| `DATABASE_URL` | No | bundled SQLite demo | SQLAlchemy connection string for your own DB (see below) |

---

## Using Your Own Database

By default the agent runs against a bundled, auto-seeded SQLite demo. To point
it at a real database, set `DATABASE_URL` (any SQLAlchemy connection string):

```bash
# Your own SQLite file
export DATABASE_URL="sqlite:///path/to/your.db"

# PostgreSQL (install a driver first: pip install "psycopg[binary]")
export DATABASE_URL="postgresql+psycopg://user:password@host:5432/dbname"

# MySQL (install a driver first: pip install pymysql)
export DATABASE_URL="mysql+pymysql://user:password@host:3306/dbname"
```

With a non-demo database the agent works against whatever schema and data
already exist — nothing is seeded. The agent reads the live schema (and the SQL
dialect) at runtime, so no code changes are needed. All guardrails still apply.

> **Safety note for live/production databases:** the read path is SELECT-only
> and low-risk, but before enabling writes against important data, connect with
> a least-privilege database role (ideally read-only for queries, and a
> write role scoped to just the tables the agent may touch), and keep the
> confirmation gate on. Treat prod writes as human-reviewed, not autonomous.

---

## How to Run

```bash
# Ask a question (read)
python main.py --query "Which city has the most customers?"

# Make a change in plain English (write) — you'll be asked to confirm
python main.py -q "Add an order for Aarav: 2 Mechanical Keyboards, placed today 2026-10-24"

# Read-only sample questions
python main.py --demo

# Plain-English create/update examples (writes)
python main.py --write-demo

# Auto-confirm writes (skip the y/N prompt) — handy for demos
python main.py --write-demo --yes

# Interactive REPL (read or write)
python main.py

# Recreate the demo database (undo any writes)
python main.py --reset-db
```

---

## Example Input & Output

### Example 1 — Read
Input:
```
"Which city has the most customers?"
```
Output:
```
> Which city has the most customers?
--------------------------------------------------------------------
  step 1: → inspect_schema()                        ← schema (1280 chars)
  step 2: → run_query(sql='SELECT city, COUNT(*) ... GROUP BY city ORDER BY ... LIMIT 5')
            ← ok, 5 row(s)
--------------------------------------------------------------------
A: Bengaluru has the most customers, with 3.
SQL: SELECT city, COUNT(*) AS customer_count FROM customers GROUP BY city ORDER BY customer_count DESC LIMIT 5;
   (2 step(s))
```

### Example 2 — Write (plain English → records, with confirmation)
Input:
```
"Place a new order for Aarav Sharma for 2 Mechanical Keyboards and 1 USB-C Hub,
 dated today with status 'placed'."
```
Output:
```
> Place a new order for Aarav Sharma for 2 Mechanical Keyboards and 1 USB-C Hub ...
--------------------------------------------------------------------
  step 1: → inspect_schema()                        ← schema (1280 chars)
  step 2: → run_query(sql="SELECT id FROM customers WHERE name = 'Aarav Sharma'")
            ← ok, 1 row(s)
  step 3: → run_query(sql="SELECT id, price FROM products WHERE name IN (...)")
            ← ok, 2 row(s)
  step 4: → execute_transaction("Create order for Aarav + 2 line items", 3 statement(s))

  ⚠  This will WRITE to the database:
     Create order for Aarav + 2 line items
       - INSERT INTO orders (customer_id, order_date, status) VALUES (1, '2026-10-24', 'placed')
       - INSERT INTO order_items (order_id, product_id, quantity) VALUES (last_insert_rowid(), 1, 2)
       - INSERT INTO order_items (order_id, product_id, quantity) VALUES (last_insert_rowid(), 2, 1)
     Proceed? [y/N] y
            ← committed, 3 row(s) affected
--------------------------------------------------------------------
A: Done — created order #13 for Aarav Sharma: 2 Mechanical Keyboards and 1 USB-C Hub
   (₹15,997), status 'placed'.
   (4 step(s))
```

*Notes:* if a query errors, you'd see an extra `← error:` line followed by a corrected retry — the self-correction loop. If any statement in the transaction fails, the trace shows `← ROLLED BACK ...` and **nothing** is written. Asking to "delete" a record produces a **soft delete** (`UPDATE ... SET is_deleted = 1`), never a hard `DELETE`.

---

## How to Test

The database and safety layer are tested **offline** (no API key / no model calls):

```bash
pip install pytest
pytest
```

These 13 tests verify seeding and schema inspection; that invalid SQL returns a structured error (not a crash); that reads are `SELECT`-only; and every write guardrail — transactions commit atomically, roll back fully on error, hard `DELETE` is blocked, soft delete works, all DDL is blocked, and the confirmation hook can abort a write. To exercise the full agent loop, set `GEMINI_API_KEY` and run `python main.py --demo` or `python main.py --write-demo`.

---

## Known Limitations

- Requires network access and a valid Gemini API key; free-tier rate limits may cause transient failures.
- Works against any SQLite / PostgreSQL / MySQL database via `DATABASE_URL`; the included test suite exercises SQLite (the default and a second file). PostgreSQL/MySQL go through the same SQLAlchemy path but have not been exercised in CI here — bring your own server and driver.
- Writes are limited to `INSERT`/`UPDATE` on a local demo database; there is no `DELETE` (soft delete only) and no schema migration path by design.
- An `UPDATE` with an overly broad `WHERE` is still a valid write — the confirmation gate (showing the exact SQL) is the backstop, so review before approving.
- Writes persist to `demo.db`; re-running `--write-demo` adds more rows. Use `--reset-db` to return to the seeded state.
- No conversation memory across runs; each instruction is handled independently.
- The model may occasionally need several steps to reach a correct query on ambiguous requests; ADK's loop handles the retries.

---

## Security & Privacy Considerations

- **Secrets Handling**: The API key is loaded from `.env` (git-ignored) or the environment; never hard-coded or logged.
- **Data Privacy**: The natural-language question, the schema, and query results are sent to the Gemini API to produce answers. Do not point this at sensitive production data without reviewing that data flow.
- **Safety**: The agent executes SQL, **not** arbitrary code or shell commands.
  - **Reads** go through a `SELECT`/`WITH`-only allowlist (multi-statements rejected) and run on a connection that is never committed, so a read cannot persist changes on any backend.
  - **Writes** go through `execute_transaction`, which enforces, in code (not left to the model): an `INSERT`/`UPDATE`-only allowlist (**no `DELETE`**, so no hard deletes — removal is a soft delete via `is_deleted = 1`); rejection of **all DDL** (`DROP`/`ALTER`/`CREATE`/`TRUNCATE`/…), so no table or database can be dropped; a **human confirmation gate** before commit; and **atomic transactions** that roll back entirely on any error.
  - These guardrails are the agent's security boundary and are covered by the offline test suite.

---

## Future Improvements

- [ ] Pluggable database backends (Postgres/MySQL) via a connection adapter.
- [ ] Optional chart/table rendering of result sets.
- [ ] Streaming responses and token-cost reporting.
- [ ] A read-only MCP server wrapper so other agents can reuse these tools.

---

## License

This project is contributed under the repository's open-source license.
