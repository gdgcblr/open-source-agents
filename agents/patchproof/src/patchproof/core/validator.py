"""Report and contract validation rules enforcing PatchProof invariants."""

from __future__ import annotations

from patchproof.core.enums import (
    CheckStatus,
    EvidenceKind,
    FindingCategory,
    FindingStatus,
    RequirementStatus,
    TrustLevel,
    Verdict,
)
from patchproof.core.models import SCHEMA_VERSION, VerificationReport


class ReportValidationError(ValueError):
    """Raised when a VerificationReport violates schema or evidence invariants."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_report(report: VerificationReport) -> list[str]:
    """Validate all cross-entity invariants on a VerificationReport.

    Returns a list of validation error strings (empty if valid).
    """
    errors: list[str] = []

    if report.schema_version != SCHEMA_VERSION:
        errors.append(
            f"Unsupported schema_version '{report.schema_version}' (expected '{SCHEMA_VERSION}')"
        )

    # 1. Unique and resolvable evidence IDs
    evidence_by_id = {}
    for item in report.evidence:
        if item.evidence_id in evidence_by_id:
            errors.append(f"Duplicate evidence_id '{item.evidence_id}' in report.evidence")
        evidence_by_id[item.evidence_id] = item

    # 2. Unique requirement IDs and valid evidence citations
    req_by_id = {}
    for req in report.requirements:
        if req.requirement_id in req_by_id:
            errors.append(f"Duplicate requirement_id '{req.requirement_id}'")
        req_by_id[req.requirement_id] = req
        for eid in req.evidence_ids:
            if eid not in evidence_by_id:
                errors.append(
                    f"Requirement '{req.requirement_id}' cites nonexistent evidence_id '{eid}'"
                )
        if req.status in {RequirementStatus.SATISFIED, RequirementStatus.VIOLATED}:
            if not req.evidence_ids:
                errors.append(
                    f"Requirement '{req.requirement_id}' has status {req.status} "
                    "without any supporting evidence_ids"
                )
            else:
                has_non_model = any(
                    evidence_by_id[eid].kind != EvidenceKind.AGENT_INFERENCE
                    and evidence_by_id[eid].trust_level != TrustLevel.MODEL_INFERENCE
                    for eid in req.evidence_ids
                    if eid in evidence_by_id
                )
                if not has_non_model:
                    errors.append(
                        f"Requirement '{req.requirement_id}' has status {req.status} "
                        "backed only by model inference"
                    )

    # 3. Findings validation
    finding_ids: set[str] = set()
    has_confirmed_defect_or_violation = any(
        r.status == RequirementStatus.VIOLATED for r in report.requirements
    )
    for finding in report.findings:
        if finding.finding_id in finding_ids:
            errors.append(f"Duplicate finding_id '{finding.finding_id}'")
        finding_ids.add(finding.finding_id)

        for req_id in finding.requirement_ids:
            if req_id not in req_by_id:
                errors.append(
                    f"Finding '{finding.finding_id}' cites unknown requirement_id '{req_id}'"
                )

        if not finding.evidence_ids and finding.status not in {
            FindingStatus.HYPOTHESIS,
            FindingStatus.UNVERIFIED,
        }:
            errors.append(
                f"Finding '{finding.finding_id}' must cite evidence_ids or be marked "
                "HYPOTHESIS/UNVERIFIED"
            )

        for eid in finding.evidence_ids:
            if eid not in evidence_by_id:
                errors.append(
                    f"Finding '{finding.finding_id}' cites nonexistent evidence_id '{eid}'"
                )

        if finding.status == FindingStatus.CONFIRMED:
            non_model_evidence = [
                evidence_by_id[eid]
                for eid in finding.evidence_ids
                if eid in evidence_by_id
                and evidence_by_id[eid].kind != EvidenceKind.AGENT_INFERENCE
                and evidence_by_id[eid].trust_level != TrustLevel.MODEL_INFERENCE
            ]
            if not non_model_evidence:
                errors.append(
                    f"CONFIRMED finding '{finding.finding_id}' requires non-model evidence"
                )
            if finding.category in {
                FindingCategory.FUNCTIONAL_DEFECT,
                FindingCategory.REQUIREMENT_GAP,
            }:
                has_confirmed_defect_or_violation = True

    # 4. Checks validation
    for check in report.checks:
        for eid in check.evidence_ids:
            if eid not in evidence_by_id:
                errors.append(
                    f"Check '{check.check_id}' cites nonexistent evidence_id '{eid}'"
                )
        if check.status in {CheckStatus.PASSED, CheckStatus.FAILED}:
            has_tool_or_static_result = any(
                evidence_by_id[eid].kind
                in {EvidenceKind.TEST_RESULT, EvidenceKind.STATIC_RESULT}
                for eid in check.evidence_ids
                if eid in evidence_by_id
            )
            if not has_tool_or_static_result:
                errors.append(
                    f"Check '{check.check_id}' has status {check.status} without a "
                    "recorded TEST_RESULT or STATIC_RESULT evidence item"
                )

    # 5. Agent runs validation
    for arun in report.agent_runs:
        for eid in arun.evidence_ids:
            if eid not in evidence_by_id:
                errors.append(
                    f"AgentRun '{arun.agent_name}' cites nonexistent evidence_id '{eid}'"
                )

    # 6. Traceability validation
    for entry in report.traceability:
        if entry.requirement_id not in req_by_id:
            errors.append(
                f"Traceability entry references unknown requirement_id '{entry.requirement_id}'"
            )
        else:
            req = req_by_id[entry.requirement_id]
            if entry.requirement_status != req.status:
                errors.append(
                    f"Traceability status mismatch for '{entry.requirement_id}': "
                    f"{entry.requirement_status} != {req.status}"
                )
        for eid in entry.evidence_ids:
            if eid not in evidence_by_id:
                errors.append(
                    f"Traceability for '{entry.requirement_id}' cites nonexistent "
                    f"evidence_id '{eid}'"
                )

    # 7. Verdict semantics
    if report.verdict == Verdict.CHANGES_REQUESTED and not has_confirmed_defect_or_violation:
        errors.append(
            "Verdict CHANGES_REQUESTED requires at least one CONFIRMED "
            "FUNCTIONAL_DEFECT/REQUIREMENT_GAP or VIOLATED requirement"
        )

    if report.verdict == Verdict.READY_FOR_HUMAN_REVIEW and has_confirmed_defect_or_violation:
        errors.append(
            "Verdict READY_FOR_HUMAN_REVIEW is invalid when a requirement is VIOLATED "
            "or a CONFIRMED defect exists"
        )

    # 8. Truncation / warning disclosure in limitations
    if report.source.truncated:
        has_truncation_limitation = any(
            "truncat" in lim.lower() or "omitted" in lim.lower() for lim in report.limitations
        )
        if not has_truncation_limitation:
            errors.append(
                "Source was truncated but report.limitations does not disclose truncation"
            )

    return errors


def assert_valid_report(report: VerificationReport) -> None:
    """Validate report and raise ReportValidationError if any invariant fails."""
    errors = validate_report(report)
    if errors:
        raise ReportValidationError(errors)

