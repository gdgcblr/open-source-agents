from __future__ import annotations

from context_orchestration.contracts import WorkerClaims
from context_orchestration.reconciler import StateReconciler

TASK = "Continue from the current state and design the PostgreSQL database schema."


def reconcile(state, claims: dict, worker="worker-1", task=TASK):
    return StateReconciler().reconcile(state, WorkerClaims.model_validate(claims), worker, task, "m")


def test_provenance_is_stamped_by_the_engine_not_the_worker(state):
    reconcile(state, {"decisions": [{"decision": "Use UUIDs", "reason": "r", "made_by": "worker-9"}],
                      "artifacts": [{"name": "schema.sql", "verified": True}]})
    assert state.decisions[0].made_by == "worker-1"
    assert state.artifacts[0].created_by == "worker-1"
    assert state.artifacts[0].verified is False


def test_the_assigned_step_is_recorded_not_the_workers_wording(state):
    report = reconcile(state, {"completed_task": "Built the whole API and deployed it"})
    assert state.completed_tasks == [TASK]
    assert any("unplanned" in w for w in report.warnings)


def test_a_claimed_fix_does_not_close_an_issue(state):
    reconcile(state, {"issues_opened": [{"description": "Token rotation unresolved", "severity": "high"}]})
    report = reconcile(state, {"issues_resolved": ["token rotation"]}, worker="worker-2")
    issue = state.issues[0]
    assert issue.status == "open"
    assert issue.resolution_claimed_by == "worker-2"
    assert report.rejected_resolutions == ["I-1"]


def test_resolving_an_unknown_issue_is_a_warning(state):
    report = reconcile(state, {"issues_resolved": ["nothing like this"]})
    assert any("unknown issue" in w for w in report.warnings)


def test_artifacts_are_versioned_never_overwritten(state):
    reconcile(state, {"artifacts": [{"name": "architecture.md", "description": "v1"}]})
    report = reconcile(state, {"artifacts": [{"name": "Architecture.md", "description": "v2"}]}, worker="worker-2")
    artifact = state.artifacts[0]
    assert len(state.artifacts) == 1
    assert artifact.version == 2
    assert artifact.created_by == "worker-1"
    assert artifact.modified_by == ["worker-2"]
    assert report.artifacts_versioned == ["architecture.md v2"]


def test_artifacts_named_only_in_the_handoff_are_flagged(state):
    report = reconcile(state, {"artifacts": [{"name": "schema.sql"}],
                               "handoff": {"artifacts_mentioned": ["schema.sql", "erd.png"]}})
    assert report.handoff_only_artifacts == ["erd.png"]
    assert {a.name for a in state.artifacts} == {"schema.sql", "erd.png"}


def test_failed_attempts_are_append_only(state):
    reconcile(state, {"failed_attempts": [{"approach": "Sessions", "reason": "no shared store"}]})
    reconcile(state, {"failed_attempts": []}, worker="worker-2")
    reconcile(state, {"failed_attempts": [{"approach": "sessions"}]}, worker="worker-3")
    assert [f.approach for f in state.failed_attempts] == ["Sessions"]


def test_duplicate_decisions_are_not_recorded_twice(state):
    reconcile(state, {"decisions": [{"decision": "Use FastAPI", "reason": "async"}]})
    report = reconcile(state, {"decisions": [{"decision": "use fastapi.", "reason": "again"}]})
    assert len(state.decisions) == 1
    assert report.decisions_duplicate == 1


def test_missing_handoff_content_is_warned_about(state):
    report = reconcile(state, {"decisions": [{"decision": "No reason given"}]})
    text = " ".join(report.warnings)
    assert "without a reason" in text
    assert "no notes for the next worker" in text
    assert "no recommended next action" in text


def test_reconcile_advances_the_turn_and_records_history(state):
    reconcile(state, {"summary": "did it", "handoff": {"notes_for_next_worker": "n"}})
    assert state.turn == 1
    assert state.history[0].worker_id == "worker-1"
    assert state.previous_worker == "worker-1"
    assert state.notes_from_previous == "n"
