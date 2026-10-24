from __future__ import annotations

import pytest

from context_orchestration.demo import DEMO_OBJECTIVE, DEMO_PLAN
from context_orchestration.gateway import MockGateway
from context_orchestration.orchestrator import Orchestrator, count_transfers
from context_orchestration.store import SQLiteStore
from context_orchestration.worker import SYSTEM_PROMPT

from conftest import make_workers


def test_the_demo_completes_with_zero_raw_transfers(demo_run):
    _, summary = demo_run
    assert summary.status == "completed"
    assert summary.turns == 5
    assert summary.workers_used == [f"worker-{i}" for i in range(1, 6)]
    assert summary.raw_conversation_transfers == 0


def test_every_call_is_exactly_one_system_and_one_briefing(demo_run, gateway):
    assert len(gateway.calls) == 5
    for _, messages in gateway.calls:
        assert [m["role"] for m in messages] == ["system", "user"]
        assert messages[0]["content"] == SYSTEM_PROMPT


def test_a_decision_from_worker_1_reaches_worker_5(demo_run, gateway):
    worker, messages = gateway.calls[-1]
    assert worker == "worker-5"
    assert "Use PostgreSQL as the primary datastore" in messages[1]["content"]


def test_the_transfer_audit_detects_a_leaked_reply():
    raw = '{"summary": "a long enough raw reply from the first worker"}'
    turns = [{"raw_output": raw, "package_text": "briefing"},
             {"raw_output": "x", "package_text": "briefing\n" + raw}]
    assert count_transfers(turns) == 1


def test_the_review_workers_fix_claim_leaves_the_issue_open(demo_run, store):
    orch, summary = demo_run
    state = store.load_state(summary.task_id)
    rotation = next(i for i in state.issues if "Refresh-token" in i.description)
    assert rotation.status == "open"
    assert rotation.resolution_claimed_by == "worker-5"


def test_artifacts_are_versioned_across_workers(demo_run, store):
    _, summary = demo_run
    state = store.load_state(summary.task_id)
    arch = next(a for a in state.artifacts if a.name == "architecture.md")
    assert arch.version == 3
    assert arch.modified_by == ["worker-2", "worker-4"]


def test_briefings_stay_inside_the_budget(store, gateway):
    orch = Orchestrator(make_workers(3), gateway, store)
    state = orch.create_task(DEMO_OBJECTIVE, DEMO_PLAN * 4)
    orch.run(state.task_id)
    assert all(t["package_tokens"] <= 1200 for t in store.turns(state.task_id))


@pytest.mark.parametrize("n", [1, 2, 3, 5, 20])
def test_steps_are_assigned_round_robin(store, gateway, n):
    orch = Orchestrator(make_workers(n), gateway, store)
    assert [orch.worker_for(i).id for i in range(6)] == [f"worker-{(i % n) + 1}" for i in range(6)]


def test_one_hundred_workers_finish_a_hundred_step_plan(store, gateway):
    orch = Orchestrator(make_workers(100), gateway, store)
    state = orch.create_task("Write a hundred notes.", [f"Write note {i}." for i in range(100)])
    summary = orch.run(state.task_id)
    assert summary.status == "completed"
    assert len(summary.workers_used) == 100
    assert summary.raw_conversation_transfers == 0


def test_a_crashed_run_resumes_from_disk(tmp_path):
    db = tmp_path / "crash.db"

    class Crashing(MockGateway):
        def complete(self, config, messages):
            if config.id == "worker-4":
                raise RuntimeError("process killed")
            return super().complete(config, messages)

    with SQLiteStore(db) as store:
        orch = Orchestrator(make_workers(5), Crashing(), store)
        task_id = orch.create_task(DEMO_OBJECTIVE, DEMO_PLAN).task_id
        with pytest.raises(RuntimeError):
            orch.run(task_id)
        assert store.load_state(task_id).turn == 3

    fresh = MockGateway()
    with SQLiteStore(db) as store:  # a new process: new store, new orchestrator
        summary = Orchestrator(make_workers(5), fresh, store).run(task_id)
        assert summary.status == "completed"
        assert [c[0] for c in fresh.calls] == ["worker-4", "worker-5"]
        # worker 4's briefing was compiled from what turn 3 left on disk
        assert "Use UUID primary keys" in fresh.calls[0][1][1]["content"]


def test_stepping_one_turn_at_a_time(orchestrator, store):
    task_id = orchestrator.create_task(DEMO_OBJECTIVE, DEMO_PLAN).task_id
    first = orchestrator.step(task_id)
    assert first.turn == 1 and store.load_state(task_id).status == "running"
    summary = orchestrator.run(task_id, max_turns=2)
    assert summary.turns == 3 and summary.status == "running"


def test_a_finished_task_does_nothing_more(demo_run):
    orch, summary = demo_run
    assert orch.step(summary.task_id) is None


def test_bad_rosters_and_tasks_are_rejected(store, gateway):
    with pytest.raises(ValueError):
        Orchestrator([], gateway, store)
    with pytest.raises(ValueError):
        Orchestrator(make_workers(1) * 2, gateway, store)
    with pytest.raises(ValueError):
        Orchestrator(make_workers(1), gateway, store).create_task("objective", [" "])
