"""Unit tests for deterministic REST JSON contract extraction and comparison."""

from __future__ import annotations

from pathlib import Path

import pytest

from analysis.contract_extractor import (
    ContractAnalysisError,
    compare_contracts,
    load_contract_json,
)


def test_detect_field_rename_customer_id() -> None:
    before = {"customer_id": "cus_123", "status": "active"}
    after = {"customerId": "cus_123", "status": "active"}
    comp = compare_contracts(before, after, required_fields=["customer_id", "status"])

    assert comp.removed_fields == ["customer_id"]
    assert comp.added_fields == ["customerId"]
    assert comp.rename_candidates == {"customer_id": "customerId"}
    assert comp.is_breaking_candidate is True


def test_detect_missing_required_field() -> None:
    before = {"customer_id": "cus_123", "status": "active", "order_total": 499}
    after = {"customer_id": "cus_123", "status": "active"}
    comp = compare_contracts(before, after, required_fields=["customer_id", "order_total"])

    assert "order_total" in comp.removed_fields
    assert "order_total" in comp.missing_required_fields
    assert comp.is_breaking_candidate is True


def test_detect_incompatible_field_type() -> None:
    before = {"customer_id": "cus_123", "amount_cents": 1500}
    after = {"customer_id": "cus_123", "amount_cents": "1500"}
    comp = compare_contracts(before, after)

    assert len(comp.type_changes) == 1
    tc = comp.type_changes[0]
    assert tc.field_path == "amount_cents"
    assert tc.before_type == "integer"
    assert tc.after_type == "string"
    assert comp.is_breaking_candidate is True


def test_safe_compatible_addition_not_breaking() -> None:
    before = {"customer_id": "cus_123", "status": "active"}
    after = {"customer_id": "cus_123", "status": "active", "display_name": "Aditi Sharma"}
    comp = compare_contracts(before, after, required_fields=["customer_id", "status"])

    assert comp.removed_fields == []
    assert comp.added_fields == ["display_name"]
    assert comp.type_changes == []
    assert comp.missing_required_fields == []
    assert comp.is_breaking_candidate is False


def test_malformed_contract_json_raises_clear_error(tmp_path: Path) -> None:
    bad_file = tmp_path / "broken.json"
    bad_file.write_text("{invalid_json: true", encoding="utf-8")

    with pytest.raises(ContractAnalysisError, match="Malformed JSON"):
        load_contract_json(bad_file)


def test_missing_contract_file_raises_clear_error(tmp_path: Path) -> None:
    missing_file = tmp_path / "does_not_exist.json"
    with pytest.raises(ContractAnalysisError, match="Contract file not found"):
        load_contract_json(missing_file)
