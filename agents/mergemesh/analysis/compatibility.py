"""Deterministic cross-repository compatibility evaluator and evidence builder."""

from __future__ import annotations

from domain.enums import VerificationState
from domain.models import (
    ConsumerFieldAccess,
    ContractComparison,
    EvidenceItem,
    Finding,
    TestExecutionResult,
)


def evaluate_compatibility(
    provider_repo: str,
    consumer_repo: str,
    contract_comparison: ContractComparison,
    consumer_accesses: list[ConsumerFieldAccess],
    combined_test_result: TestExecutionResult | None = None,
    suggested_fix_override: str = "",
) -> list[Finding]:
    """Evaluate contract changes against consumer usage and executed test outcomes."""
    findings: list[Finding] = []
    access_by_field: dict[str, list[ConsumerFieldAccess]] = {}
    for acc in consumer_accesses:
        access_by_field.setdefault(acc.field_path, []).append(acc)

    test_reproduced_failure = (
        combined_test_result is not None and combined_test_result.status == "FAIL"
    )
    test_had_error = (
        combined_test_result is not None and combined_test_result.status in {"ERROR", "TIMEOUT"}
    )

    def _determine_verification_state(is_breaking_finding: bool) -> VerificationState:
        if not is_breaking_finding:
            return "VERIFIED_COMPATIBLE"
        if test_reproduced_failure:
            return "REPRODUCED_FAILURE"
        if test_had_error:
            return "TEST_ERROR"
        return "INFERRED_RISK"

    # 1. Check removed fields that are accessed by the consumer
    for removed_field in contract_comparison.removed_fields:
        before_info = contract_comparison.before_fields[removed_field]
        replacement = contract_comparison.rename_candidates.get(removed_field)
        matching_accesses = access_by_field.get(removed_field, [])

        if matching_accesses:
            evidence: list[EvidenceItem] = [
                EvidenceItem(
                    evidence_id=f"ev_before_{removed_field}",
                    kind="provider_contract_before",
                    repo=provider_repo,
                    path=contract_comparison.provider_before_path,
                    line=None,
                    detail=f"Field '{removed_field}' ({before_info.json_type}) existed in previous provider response shape.",
                ),
                EvidenceItem(
                    evidence_id=f"ev_after_{removed_field}",
                    kind="provider_contract_after",
                    repo=provider_repo,
                    path=contract_comparison.provider_after_path,
                    line=None,
                    detail=(
                        f"Field '{removed_field}' is absent in proposed provider response; "
                        f"candidate replacement '{replacement}' is present."
                        if replacement
                        else f"Field '{removed_field}' is absent in proposed provider response."
                    ),
                ),
            ]
            for idx, acc in enumerate(matching_accesses, start=1):
                evidence.append(
                    EvidenceItem(
                        evidence_id=f"ev_consumer_{removed_field}_{idx}",
                        kind="consumer_access",
                        repo=consumer_repo,
                        path=acc.file_path,
                        line=acc.line,
                        detail=f"Consumer accesses '{removed_field}' via {acc.access_mode} ({acc.code_snippet}).",
                    )
                )

            if combined_test_result is not None and combined_test_result.status != "NOT_RUN":
                evidence.append(
                    EvidenceItem(
                        evidence_id=f"ev_test_{removed_field}",
                        kind="test_execution",
                        repo=consumer_repo,
                        path=combined_test_result.file_path,
                        line=None,
                        detail=(
                            f"Combined contract test exited with status {combined_test_result.status}: "
                            f"{combined_test_result.failure_summary or 'see test output'}"
                        ),
                        exit_code=combined_test_result.exit_code,
                    )
                )

            remediation = suggested_fix_override or (
                f"Update {consumer_repo} ({matching_accesses[0].file_path}) to read '{replacement}' "
                f"(or fall back to '{removed_field}'), or retain '{removed_field}' in {provider_repo} "
                f"for backward compatibility."
                if replacement
                else f"Restore '{removed_field}' in {provider_repo} or remove/guard access in {consumer_repo}."
            )

            ver_state = _determine_verification_state(True)
            headline_prefix = (
                "Reproduced integration failure"
                if ver_state == "REPRODUCED_FAILURE"
                else "Potential compatibility issue"
            )
            summary_msg = (
                f"{headline_prefix}: {provider_repo} removed '{removed_field}' "
                f"(renamed to '{replacement}') while {consumer_repo} still reads '{removed_field}'."
                if replacement
                else f"{headline_prefix}: {provider_repo} removed '{removed_field}' while {consumer_repo} still reads it."
            )

            findings.append(
                Finding(
                    finding_id=f"missing_{removed_field.replace('.', '_')}",
                    kind="FIELD_REMOVED_BUT_CONSUMED",
                    severity="HIGH",
                    summary=summary_msg,
                    provider_repo=provider_repo,
                    consumer_repo=consumer_repo,
                    field=removed_field,
                    replacement_candidate=replacement,
                    confidence="HIGH",
                    verification_state=ver_state,
                    suggested_remediation=remediation,
                    evidence=evidence,
                )
            )
        elif removed_field in contract_comparison.missing_required_fields:
            # Required field removed even if consumer AST didn't explicitly show subscript access
            evidence = [
                EvidenceItem(
                    evidence_id=f"ev_req_before_{removed_field}",
                    kind="provider_contract_before",
                    repo=provider_repo,
                    path=contract_comparison.provider_before_path,
                    line=None,
                    detail=f"Required field '{removed_field}' was present in before contract.",
                ),
                EvidenceItem(
                    evidence_id=f"ev_req_after_{removed_field}",
                    kind="provider_contract_after",
                    repo=provider_repo,
                    path=contract_comparison.provider_after_path,
                    line=None,
                    detail=f"Required field '{removed_field}' is missing from after contract.",
                ),
            ]
            findings.append(
                Finding(
                    finding_id=f"missing_required_{removed_field.replace('.', '_')}",
                    kind="MISSING_REQUIRED_FIELD",
                    severity="HIGH",
                    summary=f"Required contract field '{removed_field}' was removed from {provider_repo}.",
                    provider_repo=provider_repo,
                    consumer_repo=consumer_repo,
                    field=removed_field,
                    replacement_candidate=replacement,
                    confidence="HIGH",
                    verification_state=_determine_verification_state(True),
                    suggested_remediation=f"Restore required field '{removed_field}' in {provider_repo} response.",
                    evidence=evidence,
                )
            )

    # 2. Check missing required fields that were not even in before_fields
    for req_field in contract_comparison.missing_required_fields:
        if req_field not in contract_comparison.removed_fields:
            findings.append(
                Finding(
                    finding_id=f"missing_required_{req_field.replace('.', '_')}",
                    kind="MISSING_REQUIRED_FIELD",
                    severity="HIGH",
                    summary=f"Required field '{req_field}' is missing from {provider_repo} contract.",
                    provider_repo=provider_repo,
                    consumer_repo=consumer_repo,
                    field=req_field,
                    replacement_candidate=None,
                    confidence="HIGH",
                    verification_state=_determine_verification_state(True),
                    suggested_remediation=f"Include required field '{req_field}' in {provider_repo} payload.",
                    evidence=[
                        EvidenceItem(
                            evidence_id=f"ev_missing_req_{req_field}",
                            kind="provider_contract_after",
                            repo=provider_repo,
                            path=contract_comparison.provider_after_path,
                            line=None,
                            detail=f"Required field '{req_field}' is absent from {contract_comparison.provider_after_path}.",
                        )
                    ],
                )
            )

    # 3. Check incompatible field type changes
    for type_change in contract_comparison.type_changes:
        f_path = type_change.field_path
        matching_accesses = access_by_field.get(f_path, [])
        is_consumed = len(matching_accesses) > 0
        severity = "HIGH" if (is_consumed or type_change.required) else "MEDIUM"
        ev_list: list[EvidenceItem] = [
            EvidenceItem(
                evidence_id=f"ev_type_before_{f_path}",
                kind="provider_contract_before",
                repo=provider_repo,
                path=contract_comparison.provider_before_path,
                line=None,
                detail=f"Field '{f_path}' had type '{type_change.before_type}' (sample: {type_change.before_value!r}).",
            ),
            EvidenceItem(
                evidence_id=f"ev_type_after_{f_path}",
                kind="provider_contract_after",
                repo=provider_repo,
                path=contract_comparison.provider_after_path,
                line=None,
                detail=f"Field '{f_path}' changed type to '{type_change.after_type}' (sample: {type_change.after_value!r}).",
            ),
        ]
        for idx, acc in enumerate(matching_accesses, start=1):
            ev_list.append(
                EvidenceItem(
                    evidence_id=f"ev_type_consumer_{f_path}_{idx}",
                    kind="consumer_access",
                    repo=consumer_repo,
                    path=acc.file_path,
                    line=acc.line,
                    detail=f"Consumer reads '{f_path}' at line {acc.line} ({acc.code_snippet}).",
                )
            )
        if combined_test_result is not None and combined_test_result.status != "NOT_RUN":
            ev_list.append(
                EvidenceItem(
                    evidence_id=f"ev_type_test_{f_path}",
                    kind="test_execution",
                    repo=consumer_repo,
                    path=combined_test_result.file_path,
                    line=None,
                    detail=(
                        f"Combined test status {combined_test_result.status}: "
                        f"{combined_test_result.failure_summary or 'executed'}"
                    ),
                    exit_code=combined_test_result.exit_code,
                )
            )

        findings.append(
            Finding(
                finding_id=f"type_mismatch_{f_path.replace('.', '_')}",
                kind="FIELD_TYPE_CHANGED",
                severity=severity,
                summary=(
                    f"Incompatible field type change on '{f_path}': "
                    f"'{type_change.before_type}' -> '{type_change.after_type}' across {provider_repo} and {consumer_repo}."
                ),
                provider_repo=provider_repo,
                consumer_repo=consumer_repo,
                field=f_path,
                replacement_candidate=None,
                confidence="HIGH" if is_consumed else "MEDIUM",
                verification_state=_determine_verification_state(True),
                suggested_remediation=(
                    f"Preserve '{type_change.before_type}' type for '{f_path}' in {provider_repo} or "
                    f"update {consumer_repo} parsing logic to accept '{type_change.after_type}'."
                ),
                evidence=ev_list,
            )
        )

    return findings
