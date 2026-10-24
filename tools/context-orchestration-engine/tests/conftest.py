from __future__ import annotations

import pytest

from context_orchestration.contracts import ExecutionState, WorkerConfig
from context_orchestration.demo import DEMO_OBJECTIVE, DEMO_PLAN
from context_orchestration.gateway import MockGateway
from context_orchestration.orchestrator import Orchestrator
from context_orchestration.store import SQLiteStore


def make_workers(n: int) -> list[WorkerConfig]:
    return [WorkerConfig(id=f"worker-{i}", model=f"provider/model-{i}") for i in range(1, n + 1)]


@pytest.fixture()
def store(tmp_path):
    with SQLiteStore(tmp_path / "test.db") as s:
        yield s


@pytest.fixture()
def gateway():
    return MockGateway()


@pytest.fixture()
def orchestrator(store, gateway):
    return Orchestrator(make_workers(5), gateway, store)


@pytest.fixture()
def demo_run(orchestrator):
    state = orchestrator.create_task(DEMO_OBJECTIVE, DEMO_PLAN)
    summary = orchestrator.run(state.task_id)
    return orchestrator, summary


@pytest.fixture()
def state():
    return ExecutionState(task_id="task-test", objective=DEMO_OBJECTIVE, plan=list(DEMO_PLAN))
