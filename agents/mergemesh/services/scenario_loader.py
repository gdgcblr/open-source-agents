"""Scenario fixture loader and path validator."""

from __future__ import annotations

import json
from pathlib import Path

from config.settings import FIXTURES_ROOT
from domain.models import DiffFileRef, ScenarioDefinition
from execution.fixture_registry import ALLOWED_SCENARIO_IDS

SUPPORTED_INTERFACE_TYPES = {"rest_json"}


class ScenarioValidationError(ValueError):
    """Raised when a scenario definition is missing, invalid, or escapes the fixture root."""


def _ensure_within_root(root_dir: Path, relative_path: str) -> Path:
    if not relative_path or ".." in Path(relative_path).parts:
        raise ScenarioValidationError(f"Path traversal or empty path rejected: '{relative_path}'")
    resolved_root = root_dir.resolve()
    target = (resolved_root / relative_path).resolve()
    if not str(target).startswith(str(resolved_root)):
        raise ScenarioValidationError(f"Path '{relative_path}' escapes fixture root '{resolved_root}'")
    return target


def list_available_scenarios(fixtures_root: Path = FIXTURES_ROOT) -> list[ScenarioDefinition]:
    """Load all valid allow-listed scenarios in deterministic display order."""
    ordered_ids = ["customer_id_rename", "safe_optional_field"]
    scenarios: list[ScenarioDefinition] = []
    for sid in ordered_ids:
        if (fixtures_root / sid / "scenario.json").exists():
            scenarios.append(load_scenario_definition(sid, fixtures_root=fixtures_root))
    return scenarios


def load_scenario_definition(
    scenario_id: str,
    fixtures_root: Path = FIXTURES_ROOT,
    enforce_allowlist: bool = True,
) -> ScenarioDefinition:
    """Load and validate a ScenarioDefinition from `fixtures/scenarios/<scenario_id>/scenario.json`."""
    if not scenario_id or "/" in scenario_id or "\\" in scenario_id or ".." in scenario_id:
        raise ScenarioValidationError(f"Invalid scenario identifier: '{scenario_id}'")

    if enforce_allowlist and scenario_id not in ALLOWED_SCENARIO_IDS:
        raise ScenarioValidationError(
            f"Unknown or unapproved scenario ID '{scenario_id}'. "
            f"Allowed scenarios: {sorted(ALLOWED_SCENARIO_IDS)}"
        )

    scenario_dir = (fixtures_root / scenario_id).resolve()
    if not str(scenario_dir).startswith(str(fixtures_root.resolve())):
        raise ScenarioValidationError(f"Scenario directory escapes fixtures root: {scenario_id}")

    scenario_file = scenario_dir / "scenario.json"
    if not scenario_file.exists() or not scenario_file.is_file():
        raise ScenarioValidationError(f"Scenario definition file not found: {scenario_file}")

    try:
        data = json.loads(scenario_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScenarioValidationError(f"Malformed JSON in {scenario_file}: {exc}") from exc

    if not isinstance(data, dict):
        raise ScenarioValidationError(f"Scenario definition must be a JSON object in {scenario_file}")

    required_keys = [
        "id",
        "title",
        "description",
        "provider_repo",
        "consumer_repo",
        "interface_type",
        "breaking",
        "provider_before",
        "provider_after",
        "consumer_source",
        "provider_test",
        "consumer_test",
        "integration_test",
    ]
    for req_key in required_keys:
        if req_key not in data:
            raise ScenarioValidationError(f"Missing required key '{req_key}' in {scenario_file}")

    interface_type = str(data["interface_type"])
    if interface_type not in SUPPORTED_INTERFACE_TYPES:
        raise ScenarioValidationError(
            f"Unsupported interface_type '{interface_type}'. Supported: {sorted(SUPPORTED_INTERFACE_TYPES)}"
        )

    # Validate all referenced file paths exist inside the scenario directory
    for path_key in (
        "provider_before",
        "provider_after",
        "consumer_source",
        "provider_test",
        "consumer_test",
        "integration_test",
    ):
        rel = str(data[path_key])
        resolved = _ensure_within_root(scenario_dir, rel)
        if not resolved.exists() or not resolved.is_file():
            raise ScenarioValidationError(
                f"Referenced fixture file '{rel}' ({path_key}) not found in {scenario_dir}"
            )

    provider_source = str(data.get("provider_source", "repos/orders-api/provider.py"))
    if provider_source:
        _ensure_within_root(scenario_dir, provider_source)

    post_fix_test = data.get("post_fix_test")
    if post_fix_test:
        pf_resolved = _ensure_within_root(scenario_dir, str(post_fix_test))
        if not pf_resolved.exists():
            raise ScenarioValidationError(f"Referenced post_fix_test '{post_fix_test}' not found")

    post_fix_consumer = data.get("post_fix_consumer_source")
    if post_fix_consumer:
        pfc_resolved = _ensure_within_root(scenario_dir, str(post_fix_consumer))
        if not pfc_resolved.exists():
            raise ScenarioValidationError(
                f"Referenced post_fix_consumer_source '{post_fix_consumer}' not found"
            )

    diffs: list[DiffFileRef] = []
    for raw_diff in data.get("diffs", []):
        if not isinstance(raw_diff, dict):
            continue
        d_path = str(raw_diff.get("path", ""))
        d_resolved = _ensure_within_root(scenario_dir, d_path)
        if not d_resolved.exists():
            raise ScenarioValidationError(f"Diff file '{d_path}' not found in {scenario_dir}")
        diffs.append(
            DiffFileRef(
                repo=str(raw_diff.get("repo", "")),
                path=d_path,
                summary=str(raw_diff.get("summary", "")),
                content=d_resolved.read_text(encoding="utf-8"),
            )
        )

    return ScenarioDefinition(
        id=str(data["id"]),
        title=str(data["title"]),
        description=str(data["description"]),
        provider_repo=str(data["provider_repo"]),
        consumer_repo=str(data["consumer_repo"]),
        interface_type=interface_type,
        breaking=bool(data["breaking"]),
        provider_before=str(data["provider_before"]),
        provider_after=str(data["provider_after"]),
        consumer_source=str(data["consumer_source"]),
        provider_source=provider_source,
        provider_test=str(data["provider_test"]),
        consumer_test=str(data["consumer_test"]),
        integration_test=str(data["integration_test"]),
        post_fix_test=str(post_fix_test) if post_fix_test else None,
        post_fix_consumer_source=str(post_fix_consumer) if post_fix_consumer else None,
        diffs=diffs,
        required_fields=[str(x) for x in data.get("required_fields", [])],
        expected_finding_id=data.get("expected_finding_id"),
        suggested_fix=str(data.get("suggested_fix", "")),
        pr_a_title=str(data.get("pr_a_title", f"PR A ({data['provider_repo']})")),
        pr_b_title=str(data.get("pr_b_title", f"PR B ({data['consumer_repo']})")),
        consumer_mock_note=str(data.get("consumer_mock_note", "")),
        scenario_dir=str(scenario_dir),
    )
