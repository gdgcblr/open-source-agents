"""Unit tests for domain contracts, EvidenceLedger, and report validation invariants."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from patchproof.core.enums import (
    CheckStatus,
    Confidence,
    EvidenceKind,
    FindingCategory,
    FindingStatus,
    RequirementOrigin,
    RequirementStatus,
    Severity,
    SourceKind,
    TrustLevel,
    Verdict,
)
from patchproof.core.ledger import EvidenceLedger, compute_sha256
from patchproof.core.models import (
    SCHEMA_VERSION,
    CheckResult,
    CodeLocation,
    Finding,
    Requirement,
    RunInput,
    SourceRef,
    VerificationReport,
)
from patchproof.core.validator import (
    ReportValidationError,
    assert_valid_report,
    validate_report,
)
from patchproof.providers.base import ProviderError, validate_provider_payload


def _make_base_report() -> VerificationReport:
    ledger = EvidenceLedger()
    ev_src = ledger.append(
        kind=EvidenceKind.SOURCE,
        source_uri="fixture://demo/src/app.py",
        path="src/app.py",
        line_start=1,
        line_end=10,
        content="def retry_request():\n    pass\n",
        trust_level=TrustLevel.UNTRUSTED_REPO_DATA,
    )
    ev_static = ledger.append(
        kind=EvidenceKind.STATIC_RESULT,
        source_uri="check://C-001/static_ast_retry_bound",
        path="src/app.py",
        line_start=1,
        line_end=10,
        content="STATIC_AST_CHECK_PASSED",
        trust_level=TrustLevel.DETERMINISTIC_ANALYSIS,
    )
    return VerificationReport(
        schema_version=SCHEMA_VERSION,
        run_id="run_test001",
        source=SourceRef(
            kind=SourceKind.FIXTURE,
            repository="fixture/demo",
            snapshot_hash=compute_sha256("demo"),
            truncated=False,
            synthetic=True,
        ),
        verdict=Verdict.READY_FOR_HUMAN_REVIEW,
        summary="All requirements satisfied.",
        requirements=[
            Requirement(
                requirement_id="R-001",
                text="Must retry at most 3 times",
                origin=RequirementOrigin.EXPLICIT,
                status=RequirementStatus.SATISFIED,
                evidence_ids=[ev_src.evidence_id, ev_static.evidence_id],
            )
        ],
        findings=[],
        checks=[
            CheckResult(
                check_id="C-001",
                name="static-bound-check",
                status=CheckStatus.PASSED,
                command_profile="static_ast_retry_bound",
                exit_code=0,
                duration_ms=5,
                evidence_ids=[ev_static.evidence_id],
            ),
            CheckResult(
                check_id="C-002",
                name="sandbox-pytest",
                status=CheckStatus.NOT_RUN,
                command_profile="sandbox_pytest -q",
                exit_code=None,
                evidence_ids=[],
                reason_not_run="Sandbox disabled in static_only mode",
            ),
        ],
        evidence=ledger.items(),
        limitations=["Synthetic fixture"],
    )


def test_valid_base_report_passes_validation() -> None:
    report = _make_base_report()
    assert validate_report(report) == []
    assert_valid_report(report)


def test_run_input_requires_matching_source_identifier() -> None:
    with pytest.raises(ValidationError):
        RunInput(source=SourceKind.FIXTURE, fixture_id=None)
    with pytest.raises(ValidationError):
        RunInput(source=SourceKind.GITHUB, pull_request_url=None)
    with pytest.raises(ValidationError):
        RunInput(source=SourceKind.LOCAL, local_path=None)


def test_code_location_rejects_inverted_lines() -> None:
    with pytest.raises(ValidationError):
        CodeLocation(path="src/app.py", line_start=20, line_end=10)


def test_check_result_invariants_reject_fabricated_exit_codes() -> None:
    # NOT_RUN must not have an exit_code
    with pytest.raises(ValidationError):
        CheckResult(
            check_id="C-001",
            name="pytest",
            status=CheckStatus.NOT_RUN,
            command_profile="sandbox_pytest",
            exit_code=0,
            reason_not_run="Not run",
        )
    # NOT_RUN must have reason_not_run
    with pytest.raises(ValidationError):
        CheckResult(
            check_id="C-001",
            name="pytest",
            status=CheckStatus.NOT_RUN,
            command_profile="sandbox_pytest",
            exit_code=None,
            reason_not_run=None,
        )
    # PASSED must have exit_code == 0 and evidence_ids
    with pytest.raises(ValidationError):
        CheckResult(
            check_id="C-001",
            name="pytest",
            status=CheckStatus.PASSED,
            command_profile="sandbox_pytest",
            exit_code=1,
            evidence_ids=["E-001"],
        )


def test_validator_rejects_nonexistent_evidence_id() -> None:
    report = _make_base_report()
    report.findings.append(
        Finding(
            finding_id="F-001",
            category=FindingCategory.FUNCTIONAL_DEFECT,
            severity=Severity.HIGH,
            confidence=Confidence.HIGH,
            status=FindingStatus.CONFIRMED,
            title="Defect citing missing evidence",
            description="Cites E-999 which does not exist",
            requirement_ids=["R-001"],
            evidence_ids=["E-999"],
            recommended_action="Fix it",
        )
    )
    report.verdict = Verdict.CHANGES_REQUESTED
    errors = validate_report(report)
    assert any("E-999" in err for err in errors)
    with pytest.raises(ReportValidationError):
        assert_valid_report(report)


def test_validator_rejects_confirmed_finding_with_model_only_evidence() -> None:
    report = _make_base_report()
    ledger = EvidenceLedger()
    for item in report.evidence:
        ledger.append(
            kind=item.kind,
            source_uri=item.source_uri,
            content=item.content_excerpt,
            trust_level=item.trust_level,
        )
    ev_model = ledger.append(
        kind=EvidenceKind.AGENT_INFERENCE,
        source_uri="agent://reviewer",
        content="Model thinks this might fail",
        trust_level=TrustLevel.MODEL_INFERENCE,
    )
    report.evidence = ledger.items()
    report.findings.append(
        Finding(
            finding_id="F-001",
            category=FindingCategory.FUNCTIONAL_DEFECT,
            severity=Severity.HIGH,
            confidence=Confidence.LOW,
            status=FindingStatus.CONFIRMED,
            title="Unsupported model claim",
            description="Only cites model inference",
            requirement_ids=["R-001"],
            evidence_ids=[ev_model.evidence_id],
            recommended_action="Verify first",
        )
    )
    report.verdict = Verdict.CHANGES_REQUESTED
    errors = validate_report(report)
    assert any("non-model evidence" in err for err in errors)


def test_validator_enforces_verdict_consistency() -> None:
    report = _make_base_report()
    # Verdict CHANGES_REQUESTED without any violated requirement or confirmed defect is invalid
    report.verdict = Verdict.CHANGES_REQUESTED
    errors = validate_report(report)
    assert any("CHANGES_REQUESTED requires" in err for err in errors)

    # Verdict READY_FOR_HUMAN_REVIEW when a requirement is VIOLATED is invalid
    report.verdict = Verdict.READY_FOR_HUMAN_REVIEW
    report.requirements[0].status = RequirementStatus.VIOLATED
    errors2 = validate_report(report)
    assert any("READY_FOR_HUMAN_REVIEW is invalid" in err for err2 in [errors2] for err in err2)


def test_validator_requires_truncation_limitation_when_source_truncated() -> None:
    report = _make_base_report()
    report.source = SourceRef(
        kind=SourceKind.FIXTURE,
        repository="fixture/demo",
        snapshot_hash=compute_sha256("demo"),
        truncated=True,
        synthetic=True,
    )
    report.limitations = ["Synthetic fixture only"]
    errors = validate_report(report)
    assert any("does not disclose truncation" in err for err in errors)


def test_validate_provider_payload_rejects_malformed_output() -> None:
    with pytest.raises(ProviderError):
        validate_provider_payload({"invalid_field": 123}, Requirement)
    with pytest.raises(ProviderError):
        validate_provider_payload("{not-valid-json", Requirement)

