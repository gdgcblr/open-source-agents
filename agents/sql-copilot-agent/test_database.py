"""Offline tests for the database + safety layer.

These run WITHOUT an API key (no model calls) so a reviewer can verify the
tools and the read-only safety boundary in a clean environment:

    pip install pytest && pytest
"""

from __future__ import annotations

import database as db


def setup_module(_module) -> None:
    db.seed_database(force=True)


def test_schema_lists_all_tables() -> None:
    schema = db.inspect_schema()
    for table in ("customers", "products", "orders", "order_items"):
        assert f"TABLE {table}" in schema


def test_valid_select_returns_rows() -> None:
    result = db.run_query("SELECT COUNT(*) FROM customers")
    assert result["ok"] is True
    assert result["rows"][0][0] == len(db._CUSTOMERS)


def test_join_query_works() -> None:
    result = db.run_query(
        "SELECT c.city, COUNT(*) AS n FROM customers c GROUP BY c.city"
    )
    assert result["ok"] is True
    assert "city" in result["columns"]


def test_invalid_sql_returns_error_not_exception() -> None:
    result = db.run_query("SELECT * FROM does_not_exist")
    assert result["ok"] is False
    # A structured error string is returned (not raised); exact text is
    # dialect-dependent, so just assert the table name surfaces in it.
    assert "does_not_exist" in result["error"]


def test_write_statements_are_blocked() -> None:
    for sql in (
        "DELETE FROM customers",
        "DROP TABLE orders",
        "UPDATE products SET price = 0",
        "INSERT INTO customers VALUES (99, 'x', 'y', '2024-01-01')",
    ):
        result = db.run_query(sql)
        assert result["ok"] is False, f"should have blocked: {sql}"


def test_multiple_statements_are_blocked() -> None:
    result = db.run_query("SELECT 1; DROP TABLE customers")
    assert result["ok"] is False


def test_row_cap_is_enforced() -> None:
    # Cross join produces far more than MAX_ROWS rows.
    result = db.run_query("SELECT a.id FROM order_items a, order_items b")
    assert result["ok"] is True
    assert result["row_count"] <= db.MAX_ROWS
    assert result["truncated"] is True


# --------------------------------------------------------------------------- #
# Write path: execute_transaction + guardrails
# --------------------------------------------------------------------------- #
def _count(table: str) -> int:
    return db.run_query(f"SELECT COUNT(*) FROM {table}")["rows"][0][0]


def test_transaction_inserts_atomically() -> None:
    db.seed_database(force=True)
    before = _count("orders")
    result = db.execute_transaction(
        [
            "INSERT INTO orders (customer_id, order_date, status) "
            "VALUES (1, '2026-10-24', 'placed')",
            "INSERT INTO order_items (order_id, product_id, quantity) "
            "VALUES (last_insert_rowid(), 1, 2)",
        ],
        summary="New order for customer 1",
    )
    assert result["ok"] is True and result["committed"] is True
    assert _count("orders") == before + 1


def test_transaction_rolls_back_on_error() -> None:
    db.seed_database(force=True)
    before = _count("orders")
    result = db.execute_transaction(
        [
            "INSERT INTO orders (customer_id, order_date, status) "
            "VALUES (1, '2026-10-24', 'placed')",
            # Second statement fails (FK: product 999 does not exist) -> rollback.
            "INSERT INTO order_items (order_id, product_id, quantity) "
            "VALUES (last_insert_rowid(), 999, 1)",
        ],
        summary="Order that should fail",
    )
    assert result["ok"] is False and result.get("rolled_back") is True
    # The first insert must NOT have persisted — all-or-nothing.
    assert _count("orders") == before


def test_hard_delete_is_blocked() -> None:
    result = db.execute_transaction(["DELETE FROM customers WHERE id = 1"])
    assert result["ok"] is False
    assert "soft delete" in result["error"].lower()


def test_soft_delete_is_allowed() -> None:
    db.seed_database(force=True)
    result = db.execute_transaction(
        ["UPDATE customers SET is_deleted = 1 WHERE id = 8"],
        summary="Deactivate customer 8",
    )
    assert result["ok"] is True
    active = db.run_query("SELECT COUNT(*) FROM customers WHERE is_deleted = 0")
    assert active["rows"][0][0] == len(db._CUSTOMERS) - 1


def test_ddl_is_blocked() -> None:
    for sql in ("DROP TABLE orders", "ALTER TABLE orders ADD COLUMN x TEXT",
                "CREATE TABLE evil (id INT)", "TRUNCATE TABLE orders"):
        result = db.execute_transaction([sql])
        assert result["ok"] is False, f"should have blocked: {sql}"


def test_confirmation_hook_can_abort() -> None:
    db.seed_database(force=True)
    before = _count("orders")
    db.set_confirm_hook(lambda summary, statements: False)  # always decline
    try:
        result = db.execute_transaction(
            ["INSERT INTO orders (customer_id, order_date, status) "
             "VALUES (1, '2026-10-24', 'placed')"]
        )
    finally:
        db.set_confirm_hook(None)
    assert result["ok"] is False and result.get("cancelled") is True
    assert _count("orders") == before  # nothing written
