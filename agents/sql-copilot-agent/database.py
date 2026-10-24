"""Database layer for the SQL Copilot Agent.

Backed by SQLAlchemy so the same agent can talk to different databases via a
``DATABASE_URL`` connection string:

    (unset)                              -> bundled SQLite demo (auto-seeded)
    sqlite:///path/to/your.db            -> your own SQLite file
    postgresql+psycopg://user:pw@host/db -> your own PostgreSQL database
    mysql+pymysql://user:pw@host/db      -> your own MySQL database

For any database other than the bundled demo, the agent works against whatever
schema and data already exist (nothing is seeded). The guardrails below apply
to every backend.

It exposes three operations the agent uses as tools:

- ``inspect_schema``: schema + a few sample rows + the SQL dialect in use.
- ``run_query``: a single read-only SELECT/WITH statement (never commits).
- ``execute_transaction``: INSERT/UPDATE statements run atomically, behind a
  confirmation gate, with hard deletes and all DDL rejected.
"""

from __future__ import annotations

import os
import re
import sqlite3
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

# The bundled demo database lives next to this file so the agent works
# out-of-the-box with zero external setup when DATABASE_URL is not set.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo.db")
DEMO_URL = f"sqlite:///{DB_PATH}"

# Rows returned to the model are capped so a careless "SELECT *" can never blow
# up the context window or the response latency.
MAX_ROWS = 50


# --------------------------------------------------------------------------- #
# Seed data (used only for the bundled SQLite demo)
# --------------------------------------------------------------------------- #
_SCHEMA = """
CREATE TABLE customers (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    city        TEXT    NOT NULL,
    signup_date TEXT    NOT NULL,  -- ISO date (YYYY-MM-DD)
    is_deleted  INTEGER NOT NULL DEFAULT 0  -- soft-delete flag (0 = active)
);

CREATE TABLE products (
    id       INTEGER PRIMARY KEY,
    name     TEXT    NOT NULL,
    category TEXT    NOT NULL,
    price    REAL    NOT NULL,     -- unit price in INR
    is_deleted INTEGER NOT NULL DEFAULT 0  -- soft-delete flag (0 = active)
);

CREATE TABLE orders (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date  TEXT    NOT NULL,  -- ISO date (YYYY-MM-DD)
    status      TEXT    NOT NULL,  -- one of: placed, shipped, delivered, cancelled
    is_deleted  INTEGER NOT NULL DEFAULT 0  -- soft-delete flag (0 = active)
);

CREATE TABLE order_items (
    id         INTEGER PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL
);
"""

_CUSTOMERS = [
    (1, "Aarav Sharma", "Bengaluru", "2024-01-12"),
    (2, "Diya Nair", "Mumbai", "2024-02-03"),
    (3, "Vikram Reddy", "Bengaluru", "2024-02-28"),
    (4, "Meera Iyer", "Chennai", "2024-03-15"),
    (5, "Rohan Gupta", "Delhi", "2024-04-01"),
    (6, "Ananya Rao", "Bengaluru", "2024-05-22"),
    (7, "Karthik Menon", "Kochi", "2024-06-10"),
    (8, "Sana Khan", "Hyderabad", "2024-07-19"),
]

_PRODUCTS = [
    (1, "Mechanical Keyboard", "Peripherals", 6499.0),
    (2, "USB-C Hub", "Peripherals", 2999.0),
    (3, "27-inch Monitor", "Displays", 18999.0),
    (4, "Noise-Cancelling Headphones", "Audio", 12499.0),
    (5, "Webcam 1080p", "Peripherals", 3499.0),
    (6, "Laptop Stand", "Accessories", 1799.0),
    (7, "Ergonomic Mouse", "Peripherals", 2499.0),
    (8, "Standing Desk", "Furniture", 24999.0),
]

_ORDERS = [
    (1, 1, "2024-06-01", "delivered"),
    (2, 1, "2024-08-14", "delivered"),
    (3, 2, "2024-06-20", "shipped"),
    (4, 3, "2024-07-02", "delivered"),
    (5, 3, "2024-09-11", "cancelled"),
    (6, 4, "2024-07-25", "delivered"),
    (7, 5, "2024-08-05", "placed"),
    (8, 6, "2024-09-01", "delivered"),
    (9, 6, "2024-09-30", "shipped"),
    (10, 7, "2024-10-02", "delivered"),
    (11, 8, "2024-10-10", "placed"),
    (12, 1, "2024-10-18", "shipped"),
]

_ORDER_ITEMS = [
    (1, 1, 1, 1),
    (2, 1, 2, 2),
    (3, 2, 3, 1),
    (4, 3, 4, 1),
    (5, 4, 1, 1),
    (6, 4, 7, 1),
    (7, 5, 8, 1),
    (8, 6, 3, 2),
    (9, 7, 5, 1),
    (10, 8, 4, 1),
    (11, 8, 6, 1),
    (12, 9, 2, 1),
    (13, 10, 1, 1),
    (14, 10, 7, 2),
    (15, 11, 8, 1),
    (16, 12, 3, 1),
    (17, 12, 6, 1),
]


# --------------------------------------------------------------------------- #
# Connection / engine
# --------------------------------------------------------------------------- #
def database_url() -> str:
    """The active connection string (``DATABASE_URL`` or the bundled demo)."""
    return os.getenv("DATABASE_URL") or DEMO_URL


def _is_demo_sqlite() -> bool:
    return database_url() == DEMO_URL


_engine: Engine | None = None


def get_engine() -> Engine:
    """Return a cached SQLAlchemy engine for the active ``DATABASE_URL``."""
    global _engine
    if _engine is None:
        if _is_demo_sqlite():
            seed_database()
        _engine = create_engine(database_url())
        # SQLite does not enforce foreign keys unless asked to, per-connection.
        if _engine.dialect.name == "sqlite":

            @event.listens_for(_engine, "connect")
            def _enable_fk(dbapi_conn, _record):  # noqa: ANN001
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()

    return _engine


def _reset_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def dialect() -> str:
    """Name of the SQL dialect in use (e.g. ``sqlite``, ``postgresql``)."""
    return get_engine().dialect.name


# --------------------------------------------------------------------------- #
# Seeding (bundled SQLite demo only)
# --------------------------------------------------------------------------- #
def seed_database(force: bool = False) -> None:
    """Create and populate the bundled demo ``demo.db`` if needed.

    No-op when ``DATABASE_URL`` points at a non-demo database: the agent uses
    whatever schema/data already exist there. ``force=True`` recreates the demo
    from scratch (used by tests).
    """
    if not _is_demo_sqlite():
        return

    if force:
        _reset_engine()
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
    if os.path.exists(DB_PATH):
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(_SCHEMA)
        conn.executemany(
            "INSERT INTO customers (id, name, city, signup_date) VALUES (?, ?, ?, ?)",
            _CUSTOMERS,
        )
        conn.executemany(
            "INSERT INTO products (id, name, category, price) VALUES (?, ?, ?, ?)",
            _PRODUCTS,
        )
        conn.executemany(
            "INSERT INTO orders (id, customer_id, order_date, status) VALUES (?, ?, ?, ?)",
            _ORDERS,
        )
        conn.executemany(
            "INSERT INTO order_items (id, order_id, product_id, quantity) VALUES (?, ?, ?, ?)",
            _ORDER_ITEMS,
        )
        conn.commit()
    finally:
        conn.close()


def _short(exc: Exception, limit: int = 300) -> str:
    text = str(getattr(exc, "orig", exc)).strip().replace("\n", " ")
    return text[:limit]


# --------------------------------------------------------------------------- #
# Tool: inspect_schema
# --------------------------------------------------------------------------- #
def inspect_schema() -> str:
    """Return the SQL dialect, schema, and a few sample rows per table."""
    from sqlalchemy import inspect as sa_inspect

    engine = get_engine()
    insp = sa_inspect(engine)
    blocks: list[str] = [f"SQL dialect: {engine.dialect.name}"]

    with engine.connect() as conn:
        for table in sorted(insp.get_table_names()):
            cols = insp.get_columns(table)
            col_lines = [f"  {c['name']} {c['type']}" for c in cols]

            result = conn.exec_driver_sql(f"SELECT * FROM {table} LIMIT 3")
            keys = list(result.keys())
            sample_lines = [dict(zip(keys, row)) for row in result.fetchall()]

            blocks.append(
                f"TABLE {table}\n"
                + "\n".join(col_lines)
                + f"\n  sample_rows: {sample_lines}"
            )
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------- #
# Tool: run_query (read path)
# --------------------------------------------------------------------------- #
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|truncate|attach|"
    r"detach|pragma|vacuum|reindex)\b",
    re.IGNORECASE,
)


def _validate(sql: str) -> str | None:
    """Return an error string if ``sql`` is not a safe single read query."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        return "Empty query."
    if ";" in stripped:
        return "Only a single SQL statement is allowed (no semicolons)."
    lowered = stripped.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        return "Only read-only SELECT (or WITH ... SELECT) queries are allowed."
    if _FORBIDDEN.search(stripped):
        return "Query contains a disallowed keyword; only read-only SELECT is permitted."
    return None


def run_query(sql: str) -> dict[str, Any]:
    """Execute a single read-only SELECT and return a structured result.

    Runs on a connection that is never committed, so a read can never persist
    changes on any backend.

    On success: ``{"ok": True, "columns": [...], "rows": [...], "row_count": n}``
    On failure: ``{"ok": False, "error": "<message>"}`` — the agent reads this
    error and retries with a corrected query.
    """
    error = _validate(sql)
    if error:
        return {"ok": False, "error": error}

    engine = get_engine()
    try:
        with engine.connect() as conn:
            result = conn.exec_driver_sql(sql)
            columns = list(result.keys())
            rows = result.fetchmany(MAX_ROWS + 1)
            truncated = len(rows) > MAX_ROWS
            rows = rows[:MAX_ROWS]
            return {
                "ok": True,
                "columns": columns,
                "rows": [list(r) for r in rows],
                "row_count": len(rows),
                "truncated": truncated,
            }
    except SQLAlchemyError as exc:
        # Surface a compact DB error so the model can self-correct.
        return {"ok": False, "error": f"{exc.__class__.__name__}: {_short(exc)}"}


# --------------------------------------------------------------------------- #
# Tool: execute_transaction (write path)
# --------------------------------------------------------------------------- #
# Guardrails (enforced here, not left to the model):
#   1. No DDL          -> DROP / ALTER / CREATE / TRUNCATE ... are rejected,
#                         so no database or table can ever be dropped.
#   2. No hard deletes -> DELETE is rejected; records are "removed" with a
#                         soft delete (UPDATE ... SET is_deleted = 1).
#   3. Human-in-loop   -> a confirmation hook (set by the caller) must approve
#                         the statements before anything is committed.
# Only INSERT and UPDATE are allowed, and all statements run in ONE
# transaction that is rolled back entirely if any statement fails.

_DDL_VERBS = {
    "drop", "alter", "create", "truncate", "attach", "detach",
    "vacuum", "reindex", "replace",
}

# Optional confirmation gate. A caller (e.g. the CLI) sets this to a callable
# ``(summary: str, statements: list[str]) -> bool``. Returning False aborts the
# write. When unset (e.g. in tests), no prompt is required.
_confirm_hook: Any = None


def set_confirm_hook(hook: Any) -> None:
    """Register a ``(summary, statements) -> bool`` confirmation callback."""
    global _confirm_hook
    _confirm_hook = hook


def _validate_write(sql: str) -> str | None:
    """Return an error string if ``sql`` is not an allowed INSERT/UPDATE."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        return "Empty statement."
    if ";" in stripped:
        return "Each statement must be a single SQL statement (no semicolons)."
    verb = stripped.split(None, 1)[0].lower()
    if verb == "delete":
        return (
            "Hard deletes are not allowed. To remove a record, perform a soft "
            "delete instead: UPDATE <table> SET is_deleted = 1 WHERE ..."
        )
    if verb in _DDL_VERBS:
        return (
            "Schema changes are not allowed (no DROP, ALTER, CREATE, TRUNCATE, "
            "etc.). Tables and the database can never be dropped."
        )
    if verb not in {"insert", "update"}:
        return "Only INSERT and UPDATE statements are allowed in a transaction."
    return None


def execute_transaction(
    statements: list[str], summary: str = ""
) -> dict[str, Any]:
    """Run several INSERT/UPDATE statements atomically in one transaction.

    ``summary`` is a short human-readable description of the change, shown at
    the confirmation prompt.

    Guardrails: DELETE and all DDL are rejected before anything runs; a
    confirmation hook (if set) must approve; and every statement commits
    together or not at all (any error rolls the whole transaction back).

    Returns ``{"ok": True, "committed": True, ...}`` on success, or
    ``{"ok": False, ...}`` with ``rolled_back`` / ``cancelled`` and an error.
    """
    if not statements:
        return {"ok": False, "error": "No statements provided."}

    # 1. Validate every statement up front — reject the batch if any is unsafe.
    for stmt in statements:
        error = _validate_write(stmt)
        if error:
            return {"ok": False, "error": f"Rejected statement {stmt!r}: {error}"}

    # 2. Human-in-the-loop confirmation.
    if _confirm_hook is not None and not _confirm_hook(summary, statements):
        return {
            "ok": False,
            "cancelled": True,
            "error": "User declined the transaction; nothing was written.",
        }

    # 3. Execute atomically: engine.begin() commits on success and rolls the
    #    whole batch back if any statement raises.
    engine = get_engine()
    try:
        rows_affected = 0
        with engine.begin() as conn:
            for stmt in statements:
                result = conn.exec_driver_sql(stmt)
                rows_affected += max(result.rowcount or 0, 0)
        return {
            "ok": True,
            "committed": True,
            "statements_run": len(statements),
            "rows_affected": rows_affected,
        }
    except SQLAlchemyError as exc:
        return {
            "ok": False,
            "committed": False,
            "rolled_back": True,
            "error": (
                f"{exc.__class__.__name__}: {_short(exc)}. "
                "The entire transaction was rolled back."
            ),
        }
