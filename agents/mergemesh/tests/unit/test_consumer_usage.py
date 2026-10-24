"""Unit tests for AST-based consumer field usage detection."""

from __future__ import annotations

import pytest

from analysis.consumer_usage import ConsumerParseError, extract_consumer_field_accesses


def test_detect_subscript_and_get_accesses() -> None:
    code = """
def get_customer_id(payload: dict) -> str:
    return payload["customer_id"]

def is_active(payload: dict) -> bool:
    return payload.get("status") == "active"

def get_display_name(payload: dict) -> str:
    return payload.get("display_name", "Guest")
"""
    accesses = extract_consumer_field_accesses(code, consumer_repo="checkout-client", rel_file_path="client.py")
    by_field = {a.field_path: a for a in accesses}

    assert "customer_id" in by_field
    assert by_field["customer_id"].access_mode == "subscript"
    assert by_field["customer_id"].line == 3
    assert by_field["customer_id"].default_provided is False

    assert "status" in by_field
    assert by_field["status"].access_mode == "get"
    assert by_field["status"].default_provided is False

    assert "display_name" in by_field
    assert by_field["display_name"].access_mode == "get"
    assert by_field["display_name"].default_provided is True


def test_detect_nested_subscript_access() -> None:
    code = """
def extract_nested(data: dict) -> str:
    return data["customer"]["id"]
"""
    accesses = extract_consumer_field_accesses(code)
    assert len(accesses) == 1
    assert accesses[0].field_path == "customer.id"
    assert accesses[0].access_mode == "subscript"


def test_malformed_python_source_raises_parse_error() -> None:
    bad_code = "def broken(payload:\n    return payload['customer_id']"
    with pytest.raises(ConsumerParseError, match="Syntax error"):
        extract_consumer_field_accesses(bad_code)
