"""End-to-end analysis coordinator for MergeMesh (bundled fixtures and arbitrary local Git repositories)."""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from agents.workflow import build_deterministic_explanation, generate_ai_explanation
from analysis.compatibility import evaluate_compatibility
from analysis.consumer_usage import extract_consumer_field_accesses, scan_consumer_file
from analysis.contract_extractor import (
    compare_contract_files,
    compare_contracts,
    parse_contract_content,
)
from analysis.dependency_graph import build_dependency_edges, build_graphviz_dot
from analysis.evidence import compute_scenario_hashes
from analysis.git_inspector import (
    RepoInspectionError,
    discover_consumer_python_files,
    discover_provider_contract_file,
    get_repo_diff,
    read_repo_file_at_revision,
    validate_git_repository,
    validate_git_revision,
)
from config.settings import FIXTURES_ROOT, AppSettings, load_settings
from domain.models import (
    AnalysisReport,
    ConsumerFieldAccess,
    DiffFileRef,
    ScenarioDefinition,
    TestExecutionResult,
)
from execution.runner import (
    run_explicit_user_pytest,
    run_registered_test,
    run_scenario_test_suite,
)
from services.scenario_loader import load_scenario_definition

REPORT_SCHEMA_VERSION = "1.1.0"


@dataclass
class CustomRepoAnalysisRequest:
    provider_repo_path: str
    consumer_repo_path: str
    provider_base_ref: str = "HEAD~1"
    provider_target_ref: str = "HEAD"
    provider_contract_path: str = ""
    consumer_base_ref: str = ""
    consumer_target_ref: str = "HEAD"
    consumer_source_path: str = ""
    required_fields: list[str] = field(default_factory=list)
    user_approved_test_execution: bool = False
    provider_test_rel_path: str = ""
    consumer_test_rel_path: str = ""
    combined_test_rel_path: str = ""
    post_fix_test_rel_path: str = ""
    run_post_fix: bool = False


def compute_analysis_cache_key(scenario_id: str, settings: AppSettings, include_ai: bool, run_post_fix: bool) -> str:
    """Create a deterministic cache key from scenario input hashes and active provider mode."""
    scenario = load_scenario_definition(scenario_id, fixtures_root=settings.fixtures_root)
    s_root = settings.fixtures_root / scenario.id
    rel_paths = [
        scenario.provider_before,
        scenario.provider_after,
        scenario.consumer_source,
        scenario.provider_test,
        scenario.consumer_test,
        scenario.integration_test,
    ]
    hashes = compute_scenario_hashes(s_root, rel_paths)
    raw = (
        f"{scenario_id}|{settings.ai_mode}|{settings.ollama_model}|{settings.gemini_model}|"
        f"{settings.allow_local_fallback}|{include_ai}|{run_post_fix}|{sorted(hashes.items())}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _derive_overall_status(
    findings_count: int,
    test_results: list[TestExecutionResult],
    post_fix_result: TestExecutionResult | None,
) -> str:
    if post_fix_result and post_fix_result.status == "PASS":
        return "REMEDIATED_PASS"

    combined = next((t for t in test_results if t.test_kind == "combined_integration"), None)
    if combined:
        if combined.status == "FAIL":
            return "BREAKING_FAILURE_REPRODUCED"
        if combined.status in {"ERROR", "TIMEOUT"}:
            return "TEST_EXECUTION_ERROR"
        if combined.status == "PASS" and findings_count == 0:
            return "COMPATIBLE_PASS"

    if findings_count > 0:
        return "POTENTIAL_COMPATIBILITY_ISSUE"
    return "COMPATIBLE_PASS"


def run_scenario_analysis(
    scenario_id: str,
    settings: AppSettings | None = None,
    fixtures_root: Path = FIXTURES_ROOT,
    include_ai: bool = True,
    run_post_fix: bool = False,
) -> AnalysisReport:
    """Execute deterministic contract analysis, allow-listed tests, and ADK explanation on a bundled scenario."""
    active_settings = settings or load_settings()
    scenario = load_scenario_definition(scenario_id, fixtures_root=fixtures_root)
    s_root = (fixtures_root / scenario.id).resolve()

    # 1. Deterministic contract comparison + AST consumer scan
    det_start_ns = time.perf_counter_ns()
    comparison = compare_contract_files(
        before_file=s_root / scenario.provider_before,
        after_file=s_root / scenario.provider_after,
        before_rel_path=scenario.provider_before,
        after_rel_path=scenario.provider_after,
        required_fields=scenario.required_fields,
    )
    consumer_accesses = scan_consumer_file(
        file_path=s_root / scenario.consumer_source,
        consumer_repo=scenario.consumer_repo,
        rel_file_path=scenario.consumer_source,
    )
    det_duration_ms = int((time.perf_counter_ns() - det_start_ns) / 1_000_000)

    # 2. Controlled test execution (isolated provider, isolated consumer, combined integration)
    test_start_ns = time.perf_counter_ns()
    test_results = run_scenario_test_suite(
        scenario_id=scenario.id,
        fixtures_root=fixtures_root,
        timeout_seconds=active_settings.test_runner_timeout_seconds,
    )
    post_fix_result: TestExecutionResult | None = None
    if run_post_fix and scenario.post_fix_test:
        post_fix_result = run_registered_test(
            test_id=f"{scenario.id}:post_fix_integration",
            fixtures_root=fixtures_root,
            timeout_seconds=active_settings.test_runner_timeout_seconds,
        )
    test_duration_ms = int((time.perf_counter_ns() - test_start_ns) / 1_000_000)

    combined_test = next((t for t in test_results if t.test_kind == "combined_integration"), None)

    # 3. Evaluate compatibility findings with executed test evidence
    findings = evaluate_compatibility(
        provider_repo=scenario.provider_repo,
        consumer_repo=scenario.consumer_repo,
        contract_comparison=comparison,
        consumer_accesses=consumer_accesses,
        combined_test_result=combined_test,
        suggested_fix_override=scenario.suggested_fix,
    )

    # 4. Dependency graph
    post_fix_passed = bool(post_fix_result and post_fix_result.status == "PASS")
    graph_edges = build_dependency_edges(
        provider_repo=scenario.provider_repo,
        consumer_repo=scenario.consumer_repo,
        interface_type=scenario.interface_type,
    )
    graph_dot = build_graphviz_dot(
        provider_repo=scenario.provider_repo,
        consumer_repo=scenario.consumer_repo,
        findings=findings,
        post_fix_passed=post_fix_passed,
    )

    # 5. Model-assisted explanation (or deterministic fallback)
    if include_ai:
        ai_explanation = generate_ai_explanation(
            settings=active_settings,
            scenario=scenario,
            comparison=comparison,
            consumer_accesses=consumer_accesses,
            findings=findings,
            test_results=test_results,
        )
    else:
        ai_explanation = build_deterministic_explanation(
            scenario=scenario,
            comparison=comparison,
            consumer_accesses=consumer_accesses,
            findings=findings,
            test_results=test_results,
            status="SKIPPED",
            provider_label="Deterministic Summary (AI skipped)",
            model_id=None,
            fallback_reason="AI explanation skipped by caller.",
        )

    rel_paths = [
        scenario.provider_before,
        scenario.provider_after,
        scenario.consumer_source,
        scenario.provider_source,
        scenario.provider_test,
        scenario.consumer_test,
        scenario.integration_test,
    ]
    if scenario.post_fix_test:
        rel_paths.append(scenario.post_fix_test)
    if scenario.post_fix_consumer_source:
        rel_paths.append(scenario.post_fix_consumer_source)
    for d in scenario.diffs:
        rel_paths.append(d.path)

    source_hashes = compute_scenario_hashes(s_root, rel_paths)
    overall_status = _derive_overall_status(len(findings), test_results, post_fix_result)

    return AnalysisReport(
        schema_version=REPORT_SCHEMA_VERSION,
        scenario_id=scenario.id,
        scenario_title=scenario.title,
        scenario_description=scenario.description,
        run_id=f"run_{uuid.uuid4().hex[:10]}",
        created_at=datetime.now(timezone.utc).isoformat(),
        input_mode="simulated_fixture",
        provider_repo=scenario.provider_repo,
        consumer_repo=scenario.consumer_repo,
        pr_a_title=scenario.pr_a_title,
        pr_b_title=scenario.pr_b_title,
        consumer_mock_note=scenario.consumer_mock_note,
        contract_comparison=comparison,
        consumer_accesses=consumer_accesses,
        finding_list=findings,
        test_results=test_results,
        post_fix_result=post_fix_result,
        graph_edges=graph_edges,
        graph_dot=graph_dot,
        diffs=scenario.diffs,
        ai_explanation=ai_explanation,
        overall_status=overall_status,
        deterministic_duration_ms=det_duration_ms,
        test_duration_ms=test_duration_ms,
        source_hashes=source_hashes,
    )


def run_custom_repo_analysis(
    request: CustomRepoAnalysisRequest,
    settings: AppSettings | None = None,
    include_ai: bool = True,
) -> AnalysisReport:
    """Analyze user-specified local provider and consumer Git repositories across revisions."""
    active_settings = settings or load_settings()

    # 1. Validate local repositories and revisions
    provider_dir = validate_git_repository(request.provider_repo_path)
    consumer_dir = validate_git_repository(request.consumer_repo_path)

    prov_base_sha = validate_git_revision(provider_dir, request.provider_base_ref)
    prov_target_sha = validate_git_revision(provider_dir, request.provider_target_ref)
    cons_target_sha = validate_git_revision(consumer_dir, request.consumer_target_ref)
    cons_base_sha: str | None = None
    if request.consumer_base_ref and request.consumer_base_ref.strip():
        cons_base_sha = validate_git_revision(consumer_dir, request.consumer_base_ref)

    provider_repo_name = provider_dir.name
    consumer_repo_name = consumer_dir.name

    det_start_ns = time.perf_counter_ns()

    # 2. Resolve or auto-discover provider contract path and extract before/after contracts
    contract_rel = request.provider_contract_path.strip()
    if not contract_rel:
        contract_rel = discover_provider_contract_file(provider_dir, request.provider_target_ref)

    before_raw = read_repo_file_at_revision(provider_dir, request.provider_base_ref, contract_rel)
    after_raw = read_repo_file_at_revision(provider_dir, request.provider_target_ref, contract_rel)

    before_data, before_req = parse_contract_content(before_raw, source_label=contract_rel)
    after_data, after_req = parse_contract_content(after_raw, source_label=contract_rel)
    combined_req = sorted(set(request.required_fields) | before_req | after_req)

    before_label = f"{provider_repo_name}@{request.provider_base_ref}:{contract_rel}"
    after_label = f"{provider_repo_name}@{request.provider_target_ref}:{contract_rel}"

    comparison = compare_contracts(
        before_data=before_data,
        after_data=after_data,
        before_path=before_label,
        after_path=after_label,
        required_fields=combined_req,
        before_raw_content=before_raw,
        after_raw_content=after_raw,
    )

    # 3. Resolve or auto-discover consumer Python source file(s) and extract AST field accesses
    consumer_rel_input = request.consumer_source_path.strip()
    if consumer_rel_input:
        consumer_files = [consumer_rel_input]
    else:
        consumer_files = discover_consumer_python_files(consumer_dir, request.consumer_target_ref)
        if not consumer_files:
            raise RepoInspectionError(
                f"No Python consumer source files (.py) found in '{consumer_repo_name}' "
                f"at revision '{request.consumer_target_ref}'."
            )

    consumer_accesses: list[ConsumerFieldAccess] = []
    source_hashes: dict[str, str] = {
        before_label: hashlib.sha256(before_raw.encode("utf-8")).hexdigest()[:16],
        after_label: hashlib.sha256(after_raw.encode("utf-8")).hexdigest()[:16],
    }

    for c_rel in consumer_files:
        c_raw = read_repo_file_at_revision(consumer_dir, request.consumer_target_ref, c_rel)
        c_label = f"{consumer_repo_name}@{request.consumer_target_ref}:{c_rel}"
        source_hashes[c_label] = hashlib.sha256(c_raw.encode("utf-8")).hexdigest()[:16]
        extracted = extract_consumer_field_accesses(
            source_code=c_raw,
            consumer_repo=consumer_repo_name,
            rel_file_path=c_rel,
        )
        consumer_accesses.extend(extracted)

    det_duration_ms = int((time.perf_counter_ns() - det_start_ns) / 1_000_000)

    primary_c_file = consumer_accesses[0].file_path if consumer_accesses else consumer_files[0]

    # 4. Compute real Git diffs for display
    provider_diff_text = get_repo_diff(
        provider_dir,
        request.provider_base_ref,
        request.provider_target_ref,
        rel_path=contract_rel,
    )
    if cons_base_sha:
        consumer_diff_text = get_repo_diff(
            consumer_dir,
            request.consumer_base_ref,
            request.consumer_target_ref,
            rel_path=consumer_rel_input or None,
        )
    else:
        consumer_diff_text = read_repo_file_at_revision(consumer_dir, request.consumer_target_ref, primary_c_file)

    diffs = [
        DiffFileRef(
            repo=provider_repo_name,
            path=contract_rel,
            summary=f"Git diff {request.provider_base_ref}..{request.provider_target_ref} ({prov_base_sha[:7]}..{prov_target_sha[:7]})",
            content=provider_diff_text,
        ),
        DiffFileRef(
            repo=consumer_repo_name,
            path=primary_c_file,
            summary=(
                f"Git diff {request.consumer_base_ref}..{request.consumer_target_ref}"
                if cons_base_sha
                else f"Consumer source at {request.consumer_target_ref} ({cons_target_sha[:7]})"
            ),
            content=consumer_diff_text,
        ),
    ]

    # 5. Optional explicitly approved test execution
    test_start_ns = time.perf_counter_ns()
    test_results: list[TestExecutionResult] = []
    extra_py = [provider_dir, consumer_dir]

    if request.provider_test_rel_path.strip():
        test_results.append(
            run_explicit_user_pytest(
                repo_root=provider_dir,
                test_rel_path=request.provider_test_rel_path.strip(),
                label=f"{provider_repo_name} Isolated Test",
                test_kind="provider_isolated",
                user_approved=request.user_approved_test_execution,
                extra_pythonpath=extra_py,
                timeout_seconds=active_settings.test_runner_timeout_seconds,
            )
        )
    if request.consumer_test_rel_path.strip():
        test_results.append(
            run_explicit_user_pytest(
                repo_root=consumer_dir,
                test_rel_path=request.consumer_test_rel_path.strip(),
                label=f"{consumer_repo_name} Isolated Test",
                test_kind="consumer_isolated",
                user_approved=request.user_approved_test_execution,
                extra_pythonpath=extra_py,
                timeout_seconds=active_settings.test_runner_timeout_seconds,
            )
        )
    if request.combined_test_rel_path.strip():
        test_results.append(
            run_explicit_user_pytest(
                repo_root=consumer_dir,
                test_rel_path=request.combined_test_rel_path.strip(),
                label=f"Combined Integration Test ({provider_repo_name} + {consumer_repo_name})",
                test_kind="combined_integration",
                user_approved=request.user_approved_test_execution,
                extra_pythonpath=extra_py,
                timeout_seconds=active_settings.test_runner_timeout_seconds,
            )
        )

    post_fix_result: TestExecutionResult | None = None
    if request.run_post_fix and request.post_fix_test_rel_path.strip():
        post_fix_result = run_explicit_user_pytest(
            repo_root=consumer_dir,
            test_rel_path=request.post_fix_test_rel_path.strip(),
            label=f"Post-Fix Verification Test ({provider_repo_name} + {consumer_repo_name})",
            test_kind="post_fix_integration",
            user_approved=request.user_approved_test_execution,
            extra_pythonpath=extra_py,
            timeout_seconds=active_settings.test_runner_timeout_seconds,
        )

    test_duration_ms = int((time.perf_counter_ns() - test_start_ns) / 1_000_000)
    combined_test = next((t for t in test_results if t.test_kind == "combined_integration"), None)

    # 6. Evaluate compatibility findings
    findings = evaluate_compatibility(
        provider_repo=provider_repo_name,
        consumer_repo=consumer_repo_name,
        contract_comparison=comparison,
        consumer_accesses=consumer_accesses,
        combined_test_result=combined_test,
    )

    post_fix_passed = bool(post_fix_result and post_fix_result.status == "PASS")
    graph_edges = build_dependency_edges(
        provider_repo=provider_repo_name,
        consumer_repo=consumer_repo_name,
        interface_type="rest_json",
    )
    graph_dot = build_graphviz_dot(
        provider_repo=provider_repo_name,
        consumer_repo=consumer_repo_name,
        findings=findings,
        post_fix_passed=post_fix_passed,
    )

    synthetic_scenario = ScenarioDefinition(
        id=f"custom_{provider_repo_name}_{consumer_repo_name}",
        title=f"Local Repo Analysis: {provider_repo_name} ({request.provider_base_ref} -> {request.provider_target_ref}) & {consumer_repo_name} ({request.consumer_target_ref})",
        description=f"Cross-repository analysis between local Git repositories {provider_dir} and {consumer_dir}.",
        provider_repo=provider_repo_name,
        consumer_repo=consumer_repo_name,
        interface_type="rest_json",
        breaking=comparison.is_breaking_candidate,
        provider_before=before_label,
        provider_after=after_label,
        consumer_source=primary_c_file,
        provider_source=contract_rel,
        provider_test=request.provider_test_rel_path,
        consumer_test=request.consumer_test_rel_path,
        integration_test=request.combined_test_rel_path,
        post_fix_test=request.post_fix_test_rel_path or None,
        diffs=diffs,
        required_fields=combined_req,
        pr_a_title=f"{provider_repo_name}: {request.provider_base_ref} -> {request.provider_target_ref}",
        pr_b_title=f"{consumer_repo_name}: @ {request.consumer_target_ref}",
        scenario_dir=str(consumer_dir),
    )

    if include_ai:
        ai_explanation = generate_ai_explanation(
            settings=active_settings,
            scenario=synthetic_scenario,
            comparison=comparison,
            consumer_accesses=consumer_accesses,
            findings=findings,
            test_results=test_results,
        )
    else:
        ai_explanation = build_deterministic_explanation(
            scenario=synthetic_scenario,
            comparison=comparison,
            consumer_accesses=consumer_accesses,
            findings=findings,
            test_results=test_results,
            status="SKIPPED",
            provider_label="Deterministic Summary (AI skipped)",
            model_id=None,
            fallback_reason="AI explanation skipped by caller.",
        )

    overall_status = _derive_overall_status(len(findings), test_results, post_fix_result)

    return AnalysisReport(
        schema_version=REPORT_SCHEMA_VERSION,
        scenario_id=synthetic_scenario.id,
        scenario_title=synthetic_scenario.title,
        scenario_description=synthetic_scenario.description,
        run_id=f"run_{uuid.uuid4().hex[:10]}",
        created_at=datetime.now(timezone.utc).isoformat(),
        input_mode="local_git_repos",
        provider_repo=provider_repo_name,
        consumer_repo=consumer_repo_name,
        pr_a_title=synthetic_scenario.pr_a_title,
        pr_b_title=synthetic_scenario.pr_b_title,
        consumer_mock_note=(
            "Tests were not executed (static analysis only; enable explicit test approval to run pytest checks)."
            if not request.user_approved_test_execution
            else ""
        ),
        contract_comparison=comparison,
        consumer_accesses=consumer_accesses,
        finding_list=findings,
        test_results=test_results,
        post_fix_result=post_fix_result,
        graph_edges=graph_edges,
        graph_dot=graph_dot,
        diffs=diffs,
        ai_explanation=ai_explanation,
        overall_status=overall_status,
        deterministic_duration_ms=det_duration_ms,
        test_duration_ms=test_duration_ms,
        source_hashes=source_hashes,
    )
