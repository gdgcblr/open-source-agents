"""Adversarial Reviewer agent: generates falsifiable counterexample hypotheses."""

from __future__ import annotations

import time

from patchproof.agents.base import AdversarialReviewerOutput
from patchproof.core.enums import (
    AgentStatus,
    Confidence,
    FindingCategory,
    FindingStatus,
    Severity,
)
from patchproof.core.ledger import EvidenceLedger
from patchproof.core.models import (
    SCHEMA_VERSION,
    AdversarialHypothesis,
    ChangeMap,
    CheckRequest,
    CodeLocation,
    Finding,
    Requirement,
)
from patchproof.ingestion.snapshot import ContextSnapshot
from patchproof.providers.base import LLMProvider, ProviderError


class AdversarialReviewerAgent:
    """Challenges the patch and test suite by formulating falsifiable hypotheses."""

    name = "adversarial_reviewer"

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider

    def run(
        self,
        snapshot: ContextSnapshot,
        requirements: list[Requirement],
        change_map: ChangeMap,
        ledger: EvidenceLedger,
    ) -> AdversarialReviewerOutput:
        start = time.perf_counter()
        warnings: list[str] = []
        evidence_ids: list[str] = []
        if snapshot.diff_evidence_id:
            evidence_ids.append(snapshot.diff_evidence_id)
        for ev_id in snapshot.source_evidence_ids.values():
            if ev_id not in evidence_ids:
                evidence_ids.append(ev_id)

        if self._provider is not None and self._provider.name != "none":
            try:
                return self._provider.generate_structured(
                    role=self.name,
                    system_prompt=(
                        "Propose falsifiable boundary counterexample hypotheses with explicit "
                        "disproof criteria. Never mark a hypothesis as CONFIRMED."
                    ),
                    untrusted_context={
                        "changed_files": change_map.changed_files,
                        "requirements": [r.model_dump() for r in requirements],
                        "evidence_ids": evidence_ids,
                    },
                    response_schema=AdversarialReviewerOutput,
                )
            except ProviderError as exc:
                warnings.append(
                    f"Provider '{self._provider.name}' failed in {self.name} "
                    f"({exc}); used deterministic fallback."
                )

        hypotheses: list[AdversarialHypothesis] = []
        hypothesis_findings: list[Finding] = []
        targeted_checks: list[CheckRequest] = []

        primary_req_id = requirements[0].requirement_id if requirements else None
        primary_src_path = next(iter(snapshot.source_files.keys()), None)

        found_inclusive_bound = False
        bound_line = 1
        if primary_src_path and primary_src_path in snapshot.source_files:
            src_content = snapshot.source_files[primary_src_path].content
            for idx, line in enumerate(src_content.splitlines(), start=1):
                if "while " in line and "<=" in line and "retries" in line:
                    found_inclusive_bound = True
                    bound_line = idx
                    break

        if found_inclusive_bound and primary_src_path:
            h1 = AdversarialHypothesis(
                hypothesis_id="H-001",
                requirement_id=primary_req_id,
                title="Off-by-one retry limit violation at max_retries=0 and max_retries=3",
                setup=(
                    "Configure an operation callable that unconditionally raises TransientError "
                    "and record total invocation count."
                ),
                input_case="retry_request(always_failing_op, max_retries=3) and max_retries=0",
                expected_behavior=(
                    "For max_retries=3, execute 1 initial attempt + at most 3 retries "
                    "(4 calls total). For max_retries=0, execute 1 initial attempt + 0 retries "
                    "(1 call total)."
                ),
                observed_or_predicted_divergence=(
                    f"Because `{primary_src_path}:{bound_line}` uses "
                    "`while retries <= max_retries:` with `retries` initialized to 0 and "
                    "incremented after the check, the loop executes for "
                    "retries = 0, 1, ..., max_retries (performing max_retries + 1 retries, "
                    "i.e., 5 total calls for max_retries=3 and 2 total calls for max_retries=0)."
                ),
                disproof_criteria=(
                    "Disproved if static AST boundary verification or sandboxed execution shows "
                    "total invocations == 1 + max_retries when all attempts raise TransientError."
                ),
                evidence_needed=(
                    "Static AST loop-bound check result or sandboxed boundary test result."
                ),
                evidence_ids=list(evidence_ids),
                severity=Severity.HIGH,
                confidence=Confidence.HIGH,
            )
            hypotheses.append(h1)
            hypothesis_findings.append(
                Finding(
                    finding_id="F-301",
                    category=FindingCategory.FUNCTIONAL_DEFECT,
                    severity=Severity.HIGH,
                    confidence=Confidence.HIGH,
                    status=FindingStatus.HYPOTHESIS,
                    title=h1.title,
                    description=f"{h1.observed_or_predicted_divergence} (Setup: {h1.setup})",
                    requirement_ids=[primary_req_id] if primary_req_id else [],
                    evidence_ids=list(evidence_ids),
                    locations=[
                        CodeLocation(
                            path=primary_src_path,
                            line_start=bound_line,
                            line_end=bound_line,
                            symbol="retry_request",
                        )
                    ],
                    recommended_action=(
                        "Change loop condition from `while retries <= max_retries:` to "
                        "`while retries < max_retries:` and add boundary exhaustion assertions."
                    ),
                    disproof_criteria=h1.disproof_criteria,
                )
            )
            targeted_checks.append(
                CheckRequest(
                    check_id="C-001",
                    name="static-ast-retry-bound-check",
                    profile="static_ast_retry_bound",
                    args=["--strict-bounds"],
                    target_path=primary_src_path,
                    requirement_ids=[primary_req_id] if primary_req_id else [],
                    rationale="Verify or falsify H-001 off-by-one retry loop hypothesis.",
                )
            )

        h_edge = AdversarialHypothesis(
            hypothesis_id=f"H-{len(hypotheses) + 1:03d}",
            requirement_id=primary_req_id,
            title="Non-FatalClientError exceptions that are not transient may be retried",
            setup=(
                "Pass a callable that raises TypeError or KeyError (programming bug) "
                "into retry_request."
            ),
            input_case="retry_request(lambda: {}['missing'], max_retries=3)",
            expected_behavior=(
                "Only transient errors should trigger retries; programming errors or "
                "non-retryable exceptions should fail fast unless broad Exception retry "
                "is explicitly intended."
            ),
            observed_or_predicted_divergence=(
                "If `except Exception` catches all non-FatalClientError exceptions, programming "
                "errors may be retried up to max_retries times before surfacing."
            ),
            disproof_criteria=(
                "Disproved if specification explicitly mandates retrying all non-FatalClientError "
                "Exception subclasses or if catch clause is restricted to TransientError."
            ),
            evidence_needed="Clarification of intended retryable exception hierarchy.",
            evidence_ids=list(evidence_ids),
            severity=Severity.LOW,
            confidence=Confidence.MEDIUM,
        )
        hypotheses.append(h_edge)
        hypothesis_findings.append(
            Finding(
                finding_id="F-302",
                category=FindingCategory.REGRESSION_RISK,
                severity=Severity.LOW,
                confidence=Confidence.MEDIUM,
                status=FindingStatus.HYPOTHESIS,
                title=h_edge.title,
                description=h_edge.observed_or_predicted_divergence,
                requirement_ids=[primary_req_id] if primary_req_id else [],
                evidence_ids=list(evidence_ids),
                locations=(
                    [CodeLocation(path=primary_src_path, line_start=1, line_end=1)]
                    if primary_src_path
                    else []
                ),
                recommended_action=(
                    "Review whether broad `except Exception` is intended or if only "
                    "`TransientError` should be retried."
                ),
                disproof_criteria=h_edge.disproof_criteria,
            )
        )

        duration_ms = int((time.perf_counter() - start) * 1000)
        summary = (
            f"Formulated {len(hypotheses)} falsifiable adversarial hypothesis/hypotheses "
            f"and requested {len(targeted_checks)} targeted check(s)."
        )

        return AdversarialReviewerOutput(
            agent_name=self.name,
            schema_version=SCHEMA_VERSION,
            status=AgentStatus.SUCCEEDED,
            summary=summary,
            evidence_ids=evidence_ids,
            warnings=warnings,
            duration_ms=duration_ms,
            hypotheses=hypotheses,
            hypothesis_findings=hypothesis_findings,
            targeted_check_requests=targeted_checks,
        )
