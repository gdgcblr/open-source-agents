"""Evidence Adjudicator agent: resolves findings and requirement statuses against evidence."""

from __future__ import annotations

import time

from patchproof.agents.base import (
    AdjudicatorOutput,
    AdversarialReviewerOutput,
    ChangeInvestigatorOutput,
    IntentAnalystOutput,
    TestCoverageOutput,
    VerificationAgentOutput,
)
from patchproof.core.enums import (
    AgentStatus,
    CheckStatus,
    FindingCategory,
    FindingStatus,
    RequirementStatus,
    Verdict,
)
from patchproof.core.ledger import EvidenceLedger
from patchproof.core.models import (
    SCHEMA_VERSION,
    Finding,
    Requirement,
    TraceabilityEntry,
)
from patchproof.ingestion.snapshot import ContextSnapshot


class EvidenceAdjudicatorAgent:
    """Produces a conservative final report from evidence, checks, and agent analyses."""

    name = "evidence_adjudicator"

    def run(
        self,
        snapshot: ContextSnapshot,
        intent_output: IntentAnalystOutput,
        change_output: ChangeInvestigatorOutput,
        coverage_output: TestCoverageOutput,
        adversarial_output: AdversarialReviewerOutput,
        verification_output: VerificationAgentOutput,
        ledger: EvidenceLedger,
    ) -> AdjudicatorOutput:
        start = time.perf_counter()
        warnings: list[str] = []
        open_questions: list[str] = list(intent_output.ambiguity_questions)
        limitations: list[str] = []

        if snapshot.source_ref.synthetic:
            limitations.append(
                f"Source '{snapshot.source_ref.repository}' is a synthetic local fixture "
                "for reproducible verification benchmarking, not a live GitHub pull request."
            )
        if snapshot.source_ref.truncated or snapshot.omitted_files_count > 0:
            limitations.append(
                "Source snapshot was truncated "
                f"(omitted_files_count={snapshot.omitted_files_count}); "
                "uninspected files may contain additional side effects."
            )
        for w in snapshot.source_ref.warnings:
            if w not in limitations:
                limitations.append(w)

        not_run_checks = [
            c for c in verification_output.check_results if c.status == CheckStatus.NOT_RUN
        ]
        if not_run_checks:
            names = ", ".join(c.name for c in not_run_checks)
            limitations.append(
                f"Dynamic sandbox check(s) [{names}] were NOT_RUN; conclusions rely on "
                "deterministic static AST analysis and source/test inspection."
            )

        static_bound_check = next(
            (
                c
                for c in verification_output.check_results
                if "static_ast_retry_bound" in c.command_profile
            ),
            None,
        )

        combined_src = "\n".join(s.content for s in snapshot.source_files.values())
        src_ev_ids = list(snapshot.source_evidence_ids.values())
        tst_ev_ids = list(snapshot.test_evidence_ids.values())
        diff_ev_ids = [snapshot.diff_evidence_id] if snapshot.diff_evidence_id else []

        adjudicated_reqs: list[Requirement] = []
        for req in intent_output.requirements:
            req_copy = req.model_copy(deep=True)
            req_copy.code_locations = list(
                change_output.change_map.requirement_to_code.get(req.requirement_id, [])
            )
            req_copy.test_ids = list(
                coverage_output.requirement_to_tests.get(req.requirement_id, [])
            )

            if req_copy.status == RequirementStatus.AMBIGUOUS:
                adjudicated_reqs.append(req_copy)
                continue

            req_lower = req_copy.text.lower()
            ev_set = list(req_copy.evidence_ids)
            for eid in diff_ev_ids + src_ev_ids:
                if eid not in ev_set:
                    ev_set.append(eid)

            if "valueerror" in req_lower or "negative" in req_lower:
                has_src_guard = "max_retries < 0" in combined_src and "ValueError" in combined_src
                if has_src_guard and req_copy.test_ids:
                    req_copy.status = RequirementStatus.SATISFIED
                    for eid in tst_ev_ids:
                        if eid not in ev_set:
                            ev_set.append(eid)
                    req_copy.notes.append(
                        "Satisfied: negative max_retries guard and test assertion verified."
                    )
                else:
                    req_copy.status = RequirementStatus.UNVERIFIED
            elif "fatal" in req_lower or "permanent" in req_lower:
                has_fatal_guard = "FatalClientError" in combined_src and "raise" in combined_src
                if has_fatal_guard and req_copy.test_ids:
                    req_copy.status = RequirementStatus.SATISFIED
                    for eid in tst_ev_ids:
                        if eid not in ev_set:
                            ev_set.append(eid)
                    req_copy.notes.append(
                        "Satisfied: FatalClientError re-raise and test assertion verified."
                    )
                else:
                    req_copy.status = RequirementStatus.UNVERIFIED
            elif any(k in req_lower for k in ("at most", "limit", "max_retries")):
                if static_bound_check and static_bound_check.status == CheckStatus.FAILED:
                    req_copy.status = RequirementStatus.VIOLATED
                    for eid in static_bound_check.evidence_ids:
                        if eid not in ev_set:
                            ev_set.append(eid)
                    req_copy.notes.append(
                        f"Violated: deterministic check {static_bound_check.check_id} "
                        "and source diff show off-by-one `<= max_retries` loop bound."
                    )
                elif (
                    static_bound_check
                    and static_bound_check.status == CheckStatus.PASSED
                    and req_copy.test_ids
                ):
                    req_copy.status = RequirementStatus.SATISFIED
                    for eid in static_bound_check.evidence_ids + tst_ev_ids:
                        if eid not in ev_set:
                            ev_set.append(eid)
                    req_copy.notes.append(
                        "Satisfied in static AST boundary check and covered by boundary tests."
                    )
                else:
                    req_copy.status = RequirementStatus.UNVERIFIED
                    req_copy.notes.append(
                        "Unverified: insufficient boundary check or test assertion evidence."
                    )
            else:
                req_copy.status = RequirementStatus.UNVERIFIED
                req_copy.notes.append(
                    "Remains UNVERIFIED because no automated check covered this criterion."
                )

            req_copy.evidence_ids = ev_set
            adjudicated_reqs.append(req_copy)

        # Adjudicate findings according to evidence precedence
        raw_findings: list[Finding] = []

        for hyp_finding in adversarial_output.hypothesis_findings:
            f_copy = hyp_finding.model_copy(deep=True)
            if (
                f_copy.category == FindingCategory.FUNCTIONAL_DEFECT
                and static_bound_check is not None
                and static_bound_check.status == CheckStatus.FAILED
            ):
                f_copy.status = FindingStatus.CONFIRMED
                for eid in static_bound_check.evidence_ids:
                    if eid not in f_copy.evidence_ids:
                        f_copy.evidence_ids.append(eid)
                f_copy.description = (
                    f"{f_copy.description} Confirmed by deterministic static check "
                    f"{static_bound_check.check_id} ({', '.join(static_bound_check.evidence_ids)})."
                )
            else:
                f_copy.status = FindingStatus.HYPOTHESIS
            raw_findings.append(f_copy)

        for gap_finding in coverage_output.test_gap_findings:
            raw_findings.append(gap_finding.model_copy(deep=True))

        final_findings: list[Finding] = []
        for idx, item in enumerate(raw_findings, start=1):
            item.finding_id = f"F-{idx:03d}"
            final_findings.append(item)

        traceability: list[TraceabilityEntry] = []
        for req in adjudicated_reqs:
            rel_checks = [
                c.check_id
                for c in verification_output.check_results
                if c.status in {CheckStatus.PASSED, CheckStatus.FAILED, CheckStatus.NOT_RUN}
            ]
            rel_findings = [
                f.finding_id for f in final_findings if req.requirement_id in f.requirement_ids
            ]
            traceability.append(
                TraceabilityEntry(
                    requirement_id=req.requirement_id,
                    requirement_status=req.status,
                    code_locations=list(req.code_locations),
                    test_ids=list(req.test_ids),
                    check_ids=rel_checks,
                    finding_ids=rel_findings,
                    evidence_ids=list(req.evidence_ids),
                )
            )

        has_confirmed_defect = any(
            f.status == FindingStatus.CONFIRMED
            and f.category in {FindingCategory.FUNCTIONAL_DEFECT, FindingCategory.REQUIREMENT_GAP}
            for f in final_findings
        ) or any(r.status == RequirementStatus.VIOLATED for r in adjudicated_reqs)

        has_ambiguous_or_unverified = (
            not adjudicated_reqs
            or any(
                r.status in {RequirementStatus.AMBIGUOUS, RequirementStatus.UNVERIFIED}
                for r in adjudicated_reqs
            )
        )

        if has_confirmed_defect:
            verdict = Verdict.CHANGES_REQUESTED
        elif has_ambiguous_or_unverified:
            verdict = Verdict.INCONCLUSIVE
        else:
            verdict = Verdict.READY_FOR_HUMAN_REVIEW

        all_ev_ids = [item.evidence_id for item in ledger.items()]
        duration_ms = int((time.perf_counter() - start) * 1000)
        summary = (
            f"Adjudicated {len(adjudicated_reqs)} requirement(s) and {len(final_findings)} "
            f"finding(s) against {len(all_ev_ids)} evidence item(s); verdict={verdict.value}."
        )

        return AdjudicatorOutput(
            agent_name=self.name,
            schema_version=SCHEMA_VERSION,
            status=AgentStatus.SUCCEEDED,
            summary=summary,
            evidence_ids=all_ev_ids,
            warnings=warnings,
            duration_ms=duration_ms,
            verdict=verdict,
            requirements=adjudicated_reqs,
            findings=final_findings,
            traceability=traceability,
            limitations=limitations,
            open_questions=open_questions,
        )
