"""Stage A deterministic ADK tools wrapping MergeMesh's ground-truth analyzers."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from analysis.compatibility import evaluate_compatibility
from analysis.consumer_usage import extract_consumer_field_accesses, scan_consumer_file
from analysis.contract_extractor import (
    compare_contract_files,
    compare_contracts,
    parse_contract_content,
)
from analysis.git_inspector import (
    discover_consumer_python_files,
    discover_provider_contract_file,
    read_repo_file_at_revision,
    validate_git_repository,
    validate_git_revision,
)
from config.settings import FIXTURES_ROOT
from execution.runner import run_registered_test
from services.scenario_loader import load_scenario_definition


def load_scenario(scenario_id: str) -> dict[str, Any]:
    """Load a validated scenario definition by ID from the allow-listed fixture directory."""
    scenario = load_scenario_definition(scenario_id, fixtures_root=FIXTURES_ROOT)
    return asdict(scenario)


def inspect_contracts(scenario_id: str) -> dict[str, Any]:
    """Compare before and after REST JSON contracts for the given scenario."""
    scenario = load_scenario_definition(scenario_id, fixtures_root=FIXTURES_ROOT)
    s_root = FIXTURES_ROOT / scenario.id
    comp = compare_contract_files(
        before_file=s_root / scenario.provider_before,
        after_file=s_root / scenario.provider_after,
        before_rel_path=scenario.provider_before,
        after_rel_path=scenario.provider_after,
        required_fields=scenario.required_fields,
    )
    return asdict(comp)


def inspect_consumer_access(scenario_id: str) -> list[dict[str, Any]]:
    """Scan consumer source AST for dictionary/JSON field accesses."""
    scenario = load_scenario_definition(scenario_id, fixtures_root=FIXTURES_ROOT)
    s_root = FIXTURES_ROOT / scenario.id
    accesses = scan_consumer_file(
        file_path=s_root / scenario.consumer_source,
        consumer_repo=scenario.consumer_repo,
        rel_file_path=scenario.consumer_source,
    )
    return [asdict(a) for a in accesses]


def execute_allowlisted_test(scenario_id: str, test_kind: str) -> dict[str, Any]:
    """Run an allow-listed fixture test ('provider_isolated', 'consumer_isolated', 'combined_integration')."""
    test_id = f"{scenario_id}:{test_kind}"
    res = run_registered_test(test_id=test_id, fixtures_root=FIXTURES_ROOT)
    return asdict(res)


def assemble_evidence(scenario_id: str) -> list[dict[str, Any]]:
    """Assemble deterministic compatibility findings and evidence items for a scenario."""
    scenario = load_scenario_definition(scenario_id, fixtures_root=FIXTURES_ROOT)
    s_root = FIXTURES_ROOT / scenario.id
    comp = compare_contract_files(
        before_file=s_root / scenario.provider_before,
        after_file=s_root / scenario.provider_after,
        before_rel_path=scenario.provider_before,
        after_rel_path=scenario.provider_after,
        required_fields=scenario.required_fields,
    )
    accesses = scan_consumer_file(
        file_path=s_root / scenario.consumer_source,
        consumer_repo=scenario.consumer_repo,
        rel_file_path=scenario.consumer_source,
    )
    combined_res = run_registered_test(
        test_id=f"{scenario_id}:combined_integration",
        fixtures_root=FIXTURES_ROOT,
    )
    findings = evaluate_compatibility(
        provider_repo=scenario.provider_repo,
        consumer_repo=scenario.consumer_repo,
        contract_comparison=comp,
        consumer_accesses=accesses,
        combined_test_result=combined_res,
        suggested_fix_override=scenario.suggested_fix,
    )
    return [asdict(f) for f in findings]


def inspect_local_git_repos(
    provider_repo_path: str,
    consumer_repo_path: str,
    provider_base_ref: str = "HEAD~1",
    provider_target_ref: str = "HEAD",
    provider_contract_path: str = "",
    consumer_target_ref: str = "HEAD",
    consumer_source_path: str = "",
) -> list[dict[str, Any]]:
    """Inspect arbitrary local provider and consumer Git repositories and return static compatibility findings."""
    p_dir = validate_git_repository(Path(provider_repo_path))
    c_dir = validate_git_repository(Path(consumer_repo_path))
    validate_git_revision(p_dir, provider_base_ref)
    validate_git_revision(p_dir, provider_target_ref)
    validate_git_revision(c_dir, consumer_target_ref)

    c_rel = provider_contract_path.strip() or discover_provider_contract_file(p_dir, provider_target_ref)
    before_raw = read_repo_file_at_revision(p_dir, provider_base_ref, c_rel)
    after_raw = read_repo_file_at_revision(p_dir, provider_target_ref, c_rel)
    b_data, b_req = parse_contract_content(before_raw, source_label=c_rel)
    a_data, a_req = parse_contract_content(after_raw, source_label=c_rel)
    comp = compare_contracts(
        before_data=b_data,
        after_data=a_data,
        before_path=f"{p_dir.name}@{provider_base_ref}:{c_rel}",
        after_path=f"{p_dir.name}@{provider_target_ref}:{c_rel}",
        required_fields=sorted(b_req | a_req),
        before_raw_content=before_raw,
        after_raw_content=after_raw,
    )

    cons_files = [consumer_source_path.strip()] if consumer_source_path.strip() else discover_consumer_python_files(c_dir, consumer_target_ref)
    accesses = []
    for f_rel in cons_files:
        raw_py = read_repo_file_at_revision(c_dir, consumer_target_ref, f_rel)
        accesses.extend(extract_consumer_field_accesses(raw_py, consumer_repo=c_dir.name, rel_file_path=f_rel))

    findings = evaluate_compatibility(
        provider_repo=p_dir.name,
        consumer_repo=c_dir.name,
        contract_comparison=comp,
        consumer_accesses=accesses,
        combined_test_result=None,
    )
    return [asdict(f) for f in findings]


ADK_DETERMINISTIC_TOOLS = [
    load_scenario,
    inspect_contracts,
    inspect_consumer_access,
    execute_allowlisted_test,
    assemble_evidence,
    inspect_local_git_repos,
]
