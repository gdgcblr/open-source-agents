"""The State Reconciler: the only writer of canonical state.

A worker's output is a claim about what happened, not a fact. The reconciler
turns claims into canonical records under a few fixed rules:

* provenance (``made_by``, ``created_by``, turn numbers) is stamped here, never
  taken from the worker;
* the step marked complete is the step the engine assigned, not the worker's
  wording of it; an unplanned completion claim is a warning, not progress;
* artifacts are versioned, never overwritten, and are always recorded as
  unverified because nothing here inspects their content;
* an issue is never closed by a claim. The claimant is recorded on the issue
  and the issue stays open;
* failed attempts are append-only.
"""

from __future__ import annotations

from context_orchestration.contracts import (
    Artifact,
    Assumption,
    Decision,
    ExecutionState,
    FailedAttempt,
    Issue,
    ReconciliationReport,
    TurnRecord,
    WorkerClaims,
)


def norm(text: str) -> str:
    return " ".join(text.lower().split()).rstrip(".")


class StateReconciler:
    def reconcile(
        self,
        state: ExecutionState,
        claims: WorkerClaims,
        worker_id: str,
        assigned_task: str,
        model: str = "",
    ) -> ReconciliationReport:
        turn = state.turn + 1
        report = ReconciliationReport(worker_id=worker_id, turn=turn)

        self._completion(state, claims, assigned_task, report)
        self._decisions(state, claims, worker_id, turn, report)
        self._artifacts(state, claims, worker_id, turn, report)
        self._issues(state, claims, worker_id, report)

        known_failures = {norm(f.approach) for f in state.failed_attempts}
        for f in claims.failed_attempts:
            if f.approach.strip() and norm(f.approach) not in known_failures:
                state.failed_attempts.append(
                    FailedAttempt(approach=f.approach.strip(), reason=f.reason.strip(),
                                  recorded_by=worker_id, turn=turn)
                )
                known_failures.add(norm(f.approach))
                report.failed_attempts_added += 1

        known_assumptions = {norm(a.text) for a in state.assumptions}
        for a in claims.assumptions:
            if a.text.strip() and norm(a.text) not in known_assumptions:
                state.assumptions.append(
                    Assumption(text=a.text.strip(), reason=a.reason.strip(), recorded_by=worker_id)
                )
                known_assumptions.add(norm(a.text))

        handoff = claims.handoff
        state.current_progress = (
            claims.progress.strip() or handoff.state_at_handoff.strip() or state.current_progress
        )
        state.last_action = claims.last_action.strip() or claims.summary.strip()
        state.next_action = handoff.recommended_next_action.strip()
        if not state.next_action:
            report.warnings.append("handoff report has no recommended next action")
        state.notes_from_previous = handoff.notes_for_next_worker.strip()
        if not state.notes_from_previous:
            report.warnings.append("handoff report has no notes for the next worker")
        state.previous_worker = worker_id

        state.history.append(
            TurnRecord(turn=turn, worker_id=worker_id, model=model,
                       assigned_task=assigned_task, summary=claims.summary.strip())
        )
        state.turn = turn
        return report

    # -- rules -----------------------------------------------------------------

    def _completion(self, state, claims, assigned_task, report) -> None:
        if norm(assigned_task) not in {norm(t) for t in state.completed_tasks}:
            state.completed_tasks.append(assigned_task)
        claimed = claims.completed_task.strip()
        planned = {norm(p) for p in state.plan}
        if claimed and norm(claimed) != norm(assigned_task) and norm(claimed) not in planned:
            report.warnings.append(
                f"claimed completion of unplanned work, not recorded: {claimed!r}"
            )

    def _decisions(self, state, claims, worker_id, turn, report) -> None:
        known = {norm(d.decision) for d in state.decisions}
        for d in claims.decisions:
            if not d.decision.strip():
                continue
            if norm(d.decision) in known:
                report.decisions_duplicate += 1
                continue
            if not d.reason.strip():
                report.warnings.append(f"decision recorded without a reason: {d.decision!r}")
            state.decisions.append(
                Decision(decision=d.decision.strip(), reason=d.reason.strip(),
                         made_by=worker_id, turn=turn)
            )
            known.add(norm(d.decision))
            report.decisions_added += 1

    def _artifacts(self, state, claims, worker_id, turn, report) -> None:
        listed = set()
        for a in claims.artifacts:
            if a.name.strip():
                self._record_artifact(state, a.name, a.description, worker_id, turn, report)
                listed.add(norm(a.name))
        for name in claims.handoff.artifacts_mentioned:
            if not name.strip() or norm(name) in listed:
                continue
            # Named in the handoff but absent from the structured result.
            self._record_artifact(state, name, "", worker_id, turn, report)
            report.handoff_only_artifacts.append(name.strip())
            report.warnings.append(
                f"artifact {name.strip()!r} appears only in the handoff report"
            )

    def _record_artifact(self, state, name, description, worker_id, turn, report) -> None:
        existing = next((a for a in state.artifacts if norm(a.name) == norm(name)), None)
        if existing is None:
            state.artifacts.append(
                Artifact(name=name.strip(), description=description.strip(),
                         created_by=worker_id, turn=turn)
            )
            report.artifacts_created.append(name.strip())
            return
        existing.version += 1
        existing.modified_by.append(worker_id)
        existing.turn = turn
        if description.strip():
            existing.description = description.strip()
        report.artifacts_versioned.append(f"{existing.name} v{existing.version}")

    def _issues(self, state, claims, worker_id, report) -> None:
        known = {norm(i.description) for i in state.issues}
        for claimed in claims.issues_opened:
            if not claimed.description.strip() or norm(claimed.description) in known:
                continue
            issue = Issue(
                id=f"I-{len(state.issues) + 1}",
                description=claimed.description.strip(),
                severity=claimed.severity.strip().lower() or "medium",
                opened_by=worker_id,
            )
            state.issues.append(issue)
            known.add(norm(issue.description))
            report.issues_opened.append(issue.id)

        for ref in claims.issues_resolved:
            issue = self._find_issue(state, ref)
            if issue is None:
                report.warnings.append(f"claimed to resolve an unknown issue: {ref!r}")
                continue
            if issue.status == "open":
                issue.resolution_claimed_by = worker_id
                report.rejected_resolutions.append(issue.id)
                report.warnings.append(
                    f"{worker_id} claims {issue.id} is resolved; kept open until verified"
                )

    @staticmethod
    def _find_issue(state: ExecutionState, ref: str) -> Issue | None:
        key = norm(ref)
        if not key:
            return None
        for issue in state.issues:
            if norm(issue.id) == key or norm(issue.description) == key:
                return issue
        for issue in state.issues:
            if key in norm(issue.description):
                return issue
        return None
