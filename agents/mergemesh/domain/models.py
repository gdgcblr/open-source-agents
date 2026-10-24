"""Typed domain models for MergeMesh."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from domain.enums import (
    AIStatus,
    CheckStatus,
    ConfidenceLevel,
    FindingKind,
    SeverityLevel,
    VerificationState,
)


@dataclass
class DiffFileRef:
    repo: str
    path: str
    summary: str = ""
    content: str = ""


@dataclass
class ScenarioDefinition:
    id: str
    title: str
    description: str
    provider_repo: str
    consumer_repo: str
    interface_type: str
    breaking: bool
    provider_before: str
    provider_after: str
    consumer_source: str
    provider_source: str
    provider_test: str
    consumer_test: str
    integration_test: str
    post_fix_test: str | None = None
    post_fix_consumer_source: str | None = None
    diffs: list[DiffFileRef] = field(default_factory=list)
    required_fields: list[str] = field(default_factory=list)
    expected_finding_id: str | None = None
    suggested_fix: str = ""
    pr_a_title: str = ""
    pr_b_title: str = ""
    consumer_mock_note: str = ""
    scenario_dir: str = ""


@dataclass
class ContractFieldInfo:
    field_path: str
    json_type: str
    sample_value: Any
    source_path: str
    required: bool = False


@dataclass
class ContractFieldChange:
    field_path: str
    change_type: str  # "removed", "added", "type_changed", "unchanged", "missing_required"
    before_type: str | None
    after_type: str | None
    before_value: Any = None
    after_value: Any = None
    replacement_candidate: str | None = None
    required: bool = False
    impact: str = ""


@dataclass
class ContractComparison:
    provider_before_path: str
    provider_after_path: str
    before_fields: dict[str, ContractFieldInfo]
    after_fields: dict[str, ContractFieldInfo]
    removed_fields: list[str]
    added_fields: list[str]
    type_changes: list[ContractFieldChange]
    missing_required_fields: list[str]
    rename_candidates: dict[str, str]
    field_changes: list[ContractFieldChange]
    is_breaking_candidate: bool
    before_raw_content: str = ""
    after_raw_content: str = ""


@dataclass
class ConsumerFieldAccess:
    consumer_repo: str
    file_path: str
    line: int
    field_path: str
    access_mode: str  # "subscript" | "get"
    code_snippet: str = ""
    default_provided: bool = False


@dataclass
class EvidenceItem:
    evidence_id: str
    kind: str
    repo: str | None
    path: str | None
    line: int | None
    detail: str
    exit_code: int | None = None


@dataclass
class TestExecutionResult:
    __test__ = False
    test_id: str
    label: str
    test_kind: str  # "provider_isolated" | "consumer_isolated" | "combined_integration" | "post_fix_integration"
    status: CheckStatus
    exit_code: int | None
    duration_ms: int | None
    stdout: str
    stderr: str
    file_path: str
    failure_summary: str = ""
    expected_failure: bool = False
    uses_stale_mock: bool = False


@dataclass
class Finding:
    finding_id: str
    kind: FindingKind
    severity: SeverityLevel
    summary: str
    provider_repo: str
    consumer_repo: str
    field: str | None
    replacement_candidate: str | None
    confidence: ConfidenceLevel
    verification_state: VerificationState
    suggested_remediation: str = ""
    evidence: list[EvidenceItem] = field(default_factory=list)


@dataclass
class AIExplanation:
    status: AIStatus
    provider: str
    model: str | None
    summary: str
    why_it_matters: str
    observed_facts: list[str] = field(default_factory=list)
    hypotheses: list[str] = field(default_factory=list)
    suggested_fix_options: list[str] = field(default_factory=list)
    suggested_test: str | None = None
    confidence_label: str = "high"
    limitations: list[str] = field(default_factory=list)
    duration_ms: int = 0
    fallback_reason: str | None = None
    compatibility_assessment: str = ""
    severity_label: str = "high"
    remediation_tradeoffs: str = ""
    verification_plan: list[str] = field(default_factory=list)


@dataclass
class AnalysisReport:
    schema_version: str
    scenario_id: str
    scenario_title: str
    scenario_description: str
    run_id: str
    created_at: str
    input_mode: str
    provider_repo: str
    consumer_repo: str
    pr_a_title: str
    pr_b_title: str
    consumer_mock_note: str
    contract_comparison: ContractComparison
    consumer_accesses: list[ConsumerFieldAccess]
    finding_list: list[Finding]
    test_results: list[TestExecutionResult]
    post_fix_result: TestExecutionResult | None
    graph_edges: list[dict[str, str]]
    graph_dot: str
    diffs: list[DiffFileRef]
    ai_explanation: AIExplanation
    overall_status: str
    deterministic_duration_ms: int
    test_duration_ms: int
    source_hashes: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
