"""Typed Pydantic v2 domain models for PatchProof."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from patchproof.core.enums import (
    AgentStatus,
    CheckStatus,
    Confidence,
    EvidenceKind,
    ExecutionMode,
    FindingCategory,
    FindingStatus,
    ModelMode,
    RequirementOrigin,
    RequirementStatus,
    Severity,
    SourceKind,
    TrustLevel,
    Verdict,
)

SCHEMA_VERSION = "1.0"


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp string."""
    return datetime.now(UTC).isoformat()


class RunInput(BaseModel):
    """Input configuration for starting a PatchProof verification run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: SourceKind = Field(default=SourceKind.FIXTURE)
    fixture_id: str | None = Field(default=None)
    pull_request_url: str | None = Field(default=None)
    local_path: str | None = Field(default=None)
    execution_mode: ExecutionMode = Field(default=ExecutionMode.STATIC_ONLY)
    model_mode: ModelMode = Field(default=ModelMode.DETERMINISTIC)

    @model_validator(mode="after")
    def _validate_source_fields(self) -> RunInput:
        if self.source == SourceKind.FIXTURE and not (self.fixture_id and self.fixture_id.strip()):
            raise ValueError("fixture_id is required when source is 'fixture'")
        if self.source == SourceKind.GITHUB and not (
            self.pull_request_url and self.pull_request_url.strip()
        ):
            raise ValueError("pull_request_url is required when source is 'github'")
        if self.source == SourceKind.LOCAL and not (self.local_path and self.local_path.strip()):
            raise ValueError("local_path is required when source is 'local'")
        return self


class SourceRef(BaseModel):
    """Provenance and metadata for the inspected repository or fixture."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: SourceKind
    repository: str = Field(min_length=1)
    pull_request_url: str | None = Field(default=None)
    base_sha: str | None = Field(default=None)
    head_sha: str | None = Field(default=None)
    snapshot_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    truncated: bool = Field(default=False)
    synthetic: bool = Field(default=False)
    warnings: list[str] = Field(default_factory=list)


class CodeLocation(BaseModel):
    """A bounded file and optional line range / symbol reference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    symbol: str | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_line_range(self) -> CodeLocation:
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_end < self.line_start
        ):
            raise ValueError("line_end must be >= line_start")
        return self


class EvidenceItem(BaseModel):
    """A single immutable item in the append-only evidence ledger."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str = Field(pattern=r"^E-\d{3,}$")
    kind: EvidenceKind
    source_uri: str = Field(min_length=1)
    path: str | None = Field(default=None)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    content_excerpt: str
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    observed_at: str = Field(default_factory=utc_now_iso)
    trust_level: TrustLevel
    redacted: bool = Field(default=False)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_lines(self) -> EvidenceItem:
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_end < self.line_start
        ):
            raise ValueError("line_end must be >= line_start")
        return self


class Requirement(BaseModel):
    """An atomic requirement or invariant extracted from issue/PR context."""

    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(pattern=r"^R-\d{3,}$")
    text: str = Field(min_length=1)
    origin: RequirementOrigin
    status: RequirementStatus = Field(default=RequirementStatus.UNVERIFIED)
    evidence_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    code_locations: list[CodeLocation] = Field(default_factory=list)
    test_ids: list[str] = Field(default_factory=list)


class ChangedSymbol(BaseModel):
    """A function, class, or module region modified in the proposed change."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    change_summary: str = Field(min_length=1)
    observed_in_diff: bool = Field(default=True)
    evidence_id: str = Field(pattern=r"^E-\d{3,}$")


class ChangeMap(BaseModel):
    """Structured mapping of changed files, symbols, and requirement-to-code links."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    changed_files: list[str] = Field(default_factory=list)
    changed_symbols: list[ChangedSymbol] = Field(default_factory=list)
    requirement_to_code: dict[str, list[CodeLocation]] = Field(default_factory=dict)
    potential_side_effects: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class TestInventoryItem(BaseModel):
    """An existing test function discovered in the repository snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    test_id: str = Field(pattern=r"^T-\d{3,}$")
    path: str = Field(min_length=1)
    name: str = Field(min_length=1)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    assertions: list[str] = Field(default_factory=list)
    covered_requirement_ids: list[str] = Field(default_factory=list)
    evidence_id: str = Field(pattern=r"^E-\d{3,}$")


class TestProposal(BaseModel):
    """A focused verification test case proposed to close a coverage gap."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: str = Field(pattern=r"^TP-\d{3,}$")
    requirement_id: str = Field(pattern=r"^R-\d{3,}$")
    name: str = Field(min_length=1)
    preconditions: str = Field(min_length=1)
    input_summary: str = Field(min_length=1)
    expected_outcome: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class AdversarialHypothesis(BaseModel):
    """A falsifiable counterexample or edge-case hypothesis from the Adversarial Reviewer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hypothesis_id: str = Field(pattern=r"^H-\d{3,}$")
    requirement_id: str | None = Field(default=None)
    title: str = Field(min_length=1)
    setup: str = Field(min_length=1)
    input_case: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    observed_or_predicted_divergence: str = Field(min_length=1)
    disproof_criteria: str = Field(min_length=1)
    evidence_needed: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    severity: Severity = Field(default=Severity.MEDIUM)
    confidence: Confidence = Field(default=Confidence.MEDIUM)


class Finding(BaseModel):
    """A defect, gap, risk, or hypothesis recorded in the verification report."""

    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(pattern=r"^F-\d{3,}$")
    category: FindingCategory
    severity: Severity
    confidence: Confidence
    status: FindingStatus
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    requirement_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    locations: list[CodeLocation] = Field(default_factory=list)
    recommended_action: str = Field(min_length=1)
    disproof_criteria: str | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_finding_evidence(self) -> Finding:
        if self.status == FindingStatus.CONFIRMED and not self.evidence_ids:
            raise ValueError("CONFIRMED finding must cite at least one evidence_id")
        return self


class CheckRequest(BaseModel):
    """A structured verification check request submitted for policy approval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    check_id: str = Field(pattern=r"^C-\d{3,}$")
    name: str = Field(min_length=1)
    profile: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    target_path: str | None = Field(default=None)
    requirement_ids: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)


class CheckResult(BaseModel):
    """Outcome of a policy-reviewed verification check."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    check_id: str = Field(pattern=r"^C-\d{3,}$")
    name: str = Field(min_length=1)
    status: CheckStatus
    command_profile: str = Field(min_length=1)
    exit_code: int | None = Field(default=None)
    duration_ms: int | None = Field(default=None, ge=0)
    output_excerpt: str | None = Field(default=None)
    environment: str | None = Field(default=None)
    evidence_ids: list[str] = Field(default_factory=list)
    reason_not_run: str | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_check_status_invariants(self) -> CheckResult:
        if self.status in {CheckStatus.NOT_RUN, CheckStatus.REJECTED}:
            if self.exit_code is not None:
                raise ValueError(f"Check with status {self.status} must not have an exit_code")
            if not (self.reason_not_run and self.reason_not_run.strip()):
                raise ValueError(f"Check with status {self.status} must provide reason_not_run")
        if self.status == CheckStatus.PASSED:
            if self.exit_code != 0:
                raise ValueError("PASSED check requires exit_code == 0")
            if not self.evidence_ids:
                raise ValueError("PASSED check requires at least one recorded evidence_id")
        if self.status == CheckStatus.FAILED:
            if self.exit_code is None or self.exit_code == 0:
                raise ValueError("FAILED check requires a non-zero exit_code")
            if not self.evidence_ids:
                raise ValueError("FAILED check requires at least one recorded evidence_id")
        return self


class AgentRun(BaseModel):
    """Typed execution record and output summary for a logical agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_name: str = Field(min_length=1)
    schema_version: str = Field(default=SCHEMA_VERSION)
    status: AgentStatus
    summary: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duration_ms: int = Field(default=0, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)


class TraceabilityEntry(BaseModel):
    """Requirement-to-code-and-test traceability matrix row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requirement_id: str = Field(pattern=r"^R-\d{3,}$")
    requirement_status: RequirementStatus
    code_locations: list[CodeLocation] = Field(default_factory=list)
    test_ids: list[str] = Field(default_factory=list)
    check_ids: list[str] = Field(default_factory=list)
    finding_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class RunEvent(BaseModel):
    """Structured observability event recorded during a verification run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    timestamp: str = Field(default_factory=utc_now_iso)
    component: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    status: str = Field(min_length=1)
    duration_ms: int | None = Field(default=None, ge=0)
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class VerificationReport(BaseModel):
    """Top-level machine-readable and human-renderable verification report."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=SCHEMA_VERSION)
    run_id: str = Field(min_length=1)
    created_at: str = Field(default_factory=utc_now_iso)
    source: SourceRef
    verdict: Verdict
    summary: str = Field(min_length=1)
    requirements: list[Requirement] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    agent_runs: list[AgentRun] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    traceability: list[TraceabilityEntry] = Field(default_factory=list)
    test_proposals: list[TestProposal] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    events: list[RunEvent] = Field(default_factory=list)

