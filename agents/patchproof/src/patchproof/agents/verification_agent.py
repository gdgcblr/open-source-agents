"""Verification Agent: executes policy-approved static checks or sandbox checks."""

from __future__ import annotations

import time

from patchproof.agents.base import VerificationAgentOutput
from patchproof.config import PatchProofConfig
from patchproof.core.enums import (
    AgentStatus,
    CheckStatus,
    EvidenceKind,
    ExecutionMode,
    TrustLevel,
)
from patchproof.core.ledger import EvidenceLedger
from patchproof.core.models import SCHEMA_VERSION, CheckRequest, CheckResult
from patchproof.ingestion.snapshot import ContextSnapshot
from patchproof.tools.policy import evaluate_check_policy
from patchproof.tools.static_checks import run_static_ast_retry_bound_check


class VerificationAgent:
    """Executes policy-approved verification checks and records authentic results."""

    name = "verification_agent"

    def __init__(self, config: PatchProofConfig) -> None:
        self._config = config

    def run(
        self,
        snapshot: ContextSnapshot,
        check_requests: list[CheckRequest],
        execution_mode: ExecutionMode,
        ledger: EvidenceLedger,
    ) -> VerificationAgentOutput:
        start = time.perf_counter()
        warnings: list[str] = []
        evidence_ids: list[str] = []
        results: list[CheckResult] = []

        seen_ids: set[str] = set()
        deduped_requests: list[CheckRequest] = []
        for req in check_requests:
            if req.check_id not in seen_ids:
                seen_ids.add(req.check_id)
                deduped_requests.append(req)

        for req in deduped_requests:
            decision = evaluate_check_policy(req)
            if not decision.approved:
                warnings.append(f"Check '{req.check_id}' ({req.name}) rejected: {decision.reason}")
                results.append(
                    CheckResult(
                        check_id=req.check_id,
                        name=req.name,
                        status=CheckStatus.REJECTED,
                        command_profile=req.profile,
                        exit_code=None,
                        duration_ms=None,
                        output_excerpt=None,
                        environment=None,
                        evidence_ids=[],
                        reason_not_run=decision.reason,
                    )
                )
                continue

            if req.profile == "static_ast_retry_bound":
                chk_start = time.perf_counter()
                outcome = run_static_ast_retry_bound_check(snapshot, req.target_path)
                chk_ms = int((time.perf_counter() - chk_start) * 1000)
                ev = ledger.append(
                    kind=EvidenceKind.STATIC_RESULT,
                    source_uri=f"check://{req.check_id}/{req.profile}",
                    path=outcome.path,
                    line_start=outcome.line_start,
                    line_end=outcome.line_end,
                    content=outcome.summary,
                    trust_level=TrustLevel.DETERMINISTIC_ANALYSIS,
                    metadata={
                        "check_id": req.check_id,
                        "profile": req.profile,
                        "exit_code": outcome.exit_code,
                    },
                )
                evidence_ids.append(ev.evidence_id)
                results.append(
                    CheckResult(
                        check_id=req.check_id,
                        name=req.name,
                        status=CheckStatus.PASSED if outcome.passed else CheckStatus.FAILED,
                        command_profile=f"{req.profile} {' '.join(req.args)}".strip(),
                        exit_code=outcome.exit_code,
                        duration_ms=chk_ms,
                        output_excerpt=outcome.summary,
                        environment="in-memory-python-ast",
                        evidence_ids=[ev.evidence_id],
                        reason_not_run=None,
                    )
                )
            elif req.profile == "sandbox_pytest":
                if execution_mode == ExecutionMode.STATIC_ONLY or not self._config.enable_sandbox:
                    reason = (
                        "Sandbox test execution was not run (execution_mode="
                        f"'{execution_mode.value}', enable_sandbox={self._config.enable_sandbox}); "
                        "host execution fallback is strictly prohibited."
                    )
                else:
                    reason = (
                        "Disposable container sandbox is not configured or unavailable; "
                        "marked NOT_RUN without host fallback."
                    )
                results.append(
                    CheckResult(
                        check_id=req.check_id,
                        name=req.name,
                        status=CheckStatus.NOT_RUN,
                        command_profile=f"{req.profile} {' '.join(req.args)}".strip(),
                        exit_code=None,
                        duration_ms=None,
                        output_excerpt=None,
                        environment=None,
                        evidence_ids=[],
                        reason_not_run=reason,
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check_id=req.check_id,
                        name=req.name,
                        status=CheckStatus.NOT_RUN,
                        command_profile=req.profile,
                        exit_code=None,
                        duration_ms=None,
                        output_excerpt=None,
                        environment=None,
                        evidence_ids=[],
                        reason_not_run=(
                            f"Profile '{req.profile}' has no active runner in current mode."
                        ),
                    )
                )

        duration_ms = int((time.perf_counter() - start) * 1000)
        passed_cnt = sum(1 for r in results if r.status == CheckStatus.PASSED)
        failed_cnt = sum(1 for r in results if r.status == CheckStatus.FAILED)
        not_run_cnt = sum(1 for r in results if r.status == CheckStatus.NOT_RUN)
        rejected_cnt = sum(1 for r in results if r.status == CheckStatus.REJECTED)
        summary = (
            f"Processed {len(results)} check(s): {passed_cnt} PASSED, {failed_cnt} FAILED, "
            f"{not_run_cnt} NOT_RUN, {rejected_cnt} REJECTED."
        )

        return VerificationAgentOutput(
            agent_name=self.name,
            schema_version=SCHEMA_VERSION,
            status=AgentStatus.SUCCEEDED,
            summary=summary,
            evidence_ids=evidence_ids,
            warnings=warnings,
            duration_ms=duration_ms,
            check_results=results,
        )
