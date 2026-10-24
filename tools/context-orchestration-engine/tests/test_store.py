from __future__ import annotations

import pytest

from context_orchestration.contracts import WorkerConfig
from context_orchestration.demo import DEMO_OBJECTIVE, DEMO_PLAN
from context_orchestration.orchestrator import Orchestrator


def test_every_turn_is_persisted(demo_run, store):
    _, summary = demo_run
    turns = store.turns(summary.task_id)
    assert [t["turn"] for t in turns] == [1, 2, 3, 4, 5]
    assert all(t["package_text"].startswith("YOUR ASSIGNED TASK") for t in turns)


def test_state_round_trips(demo_run, store):
    _, summary = demo_run
    state = store.load_state(summary.task_id)
    assert state.status == "completed"
    assert len(state.completed_tasks) == 5


def test_prefix_resolution(demo_run, store):
    _, summary = demo_run
    assert store.resolve(summary.task_id[:9]) == summary.task_id
    with pytest.raises(KeyError):
        store.resolve("task-nope")


def test_tasks_listing(demo_run, store):
    rows = store.tasks()
    assert rows[0]["status"] == "completed" and rows[0]["turn"] == 5


def test_a_key_is_never_written_to_the_database(store, gateway, tmp_path):
    secret = "sk-must-never-be-persisted"
    worker = WorkerConfig(id="worker-1", model="m", api_key=secret)
    assert secret not in worker.model_dump_json()
    orch = Orchestrator([worker], gateway, store)
    orch.run(orch.create_task(DEMO_OBJECTIVE, DEMO_PLAN[:1]).task_id)
    store.close()
    assert secret.encode() not in (tmp_path / "test.db").read_bytes()
