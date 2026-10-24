"""Unit tests for scenario loader validation and path-traversal safety."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from execution.fixture_registry import resolve_registered_test_path
from services.scenario_loader import ScenarioValidationError, load_scenario_definition


def test_load_golden_scenarios_valid(fixtures_root: Path) -> None:
    s1 = load_scenario_definition("customer_id_rename", fixtures_root=fixtures_root)
    assert s1.id == "customer_id_rename"
    assert s1.provider_repo == "orders-api"
    assert s1.consumer_repo == "checkout-client"
    assert s1.breaking is True
    assert len(s1.diffs) == 2

    s2 = load_scenario_definition("safe_optional_field", fixtures_root=fixtures_root)
    assert s2.id == "safe_optional_field"
    assert s2.breaking is False


def test_reject_path_traversal_and_unknown_scenario(fixtures_root: Path) -> None:
    with pytest.raises(ScenarioValidationError):
        load_scenario_definition("../outside", fixtures_root=fixtures_root)

    with pytest.raises(ScenarioValidationError, match="Unknown or unapproved scenario ID"):
        load_scenario_definition("arbitrary_unregistered_scenario", fixtures_root=fixtures_root)


def test_reject_escaped_file_path_inside_scenario_json(tmp_path: Path) -> None:
    scen_dir = tmp_path / "custom_scen"
    scen_dir.mkdir(parents=True)
    bad_json = {
        "id": "custom_scen",
        "title": "Bad Scenario",
        "description": "Tests path escape",
        "provider_repo": "orders-api",
        "consumer_repo": "checkout-client",
        "interface_type": "rest_json",
        "breaking": True,
        "provider_before": "../../secret.json",
        "provider_after": "contracts/provider_after.json",
        "consumer_source": "repos/checkout-client/client.py",
        "provider_test": "repos/orders-api/tests/test_provider_unit.py",
        "consumer_test": "repos/checkout-client/tests/test_consumer_unit.py",
        "integration_test": "repos/checkout-client/tests/test_combined_contract.py",
    }
    (scen_dir / "scenario.json").write_text(json.dumps(bad_json), encoding="utf-8")

    with pytest.raises(ScenarioValidationError, match="Path traversal"):
        load_scenario_definition("custom_scen", fixtures_root=tmp_path, enforce_allowlist=False)


def test_disallow_unregistered_test_execution() -> None:
    with pytest.raises(PermissionError, match="not in the allow-listed fixture registry"):
        resolve_registered_test_path("arbitrary_repo:arbitrary_command")
