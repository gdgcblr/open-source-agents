"""The loop: compile a briefing, run one worker, reconcile, persist. Repeat.

Turns are strictly sequential. Plan step ``i`` goes to worker ``i % N``, so a
roster shorter than the plan cycles and a longer one leaves the surplus idle.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Callable

from context_orchestration.compiler import ContextCompiler
from context_orchestration.contracts import (
    ContextPackage,
    ExecutionState,
    ReconciliationReport,
    WorkerConfig,
)
from context_orchestration.gateway import Gateway
from context_orchestration.reconciler import StateReconciler
from context_orchestration.store import SQLiteStore
from context_orchestration.worker import UniversalWorker

# Raw text shorter than this is too generic to count as a leaked transcript.
TRANSFER_MIN_CHARS = 40


@dataclass
class TurnResult:
    turn: int
    worker: WorkerConfig
    assigned_task: str
    package: ContextPackage
    report: ReconciliationReport
    state: ExecutionState


@dataclass
class RunSummary:
    task_id: str
    status: str
    turns: int
    steps: int
    workers_used: list[str] = field(default_factory=list)
    raw_conversation_transfers: int = 0
    peak_package_tokens: int = 0


def load_workers(path: str | Path | None = None) -> list[WorkerConfig]:
    """``./workers.json`` if present, else the packaged five-worker example."""
    if path is None and Path("workers.json").is_file():
        path = "workers.json"
    if path is None:
        text = resources.files("context_orchestration").joinpath("workers.example.json").read_text("utf-8")
    else:
        text = Path(path).read_text(encoding="utf-8")
    entries = json.loads(text)["workers"]
    return [WorkerConfig(**e) for e in entries if e.get("enabled", True)]


def missing_keys(workers: list[WorkerConfig]) -> list[str]:
    return [w.id for w in workers if not w.resolve_key()]


class Orchestrator:
    def __init__(
        self,
        workers: list[WorkerConfig],
        gateway: Gateway,
        store: SQLiteStore,
        compiler: ContextCompiler | None = None,
        reconciler: StateReconciler | None = None,
        on_turn: Callable[[TurnResult], None] | None = None,
    ) -> None:
        if not workers:
            raise ValueError("at least one worker is required")
        ids = [w.id for w in workers]
        if len(set(ids)) != len(ids):
            raise ValueError(f"worker ids must be unique: {ids}")
        self.workers = workers
        self.gateway = gateway
        self.store = store
        self.compiler = compiler or ContextCompiler()
        self.reconciler = reconciler or StateReconciler()
        self.on_turn = on_turn

    def worker_for(self, step_index: int) -> WorkerConfig:
        return self.workers[step_index % len(self.workers)]

    def create_task(self, objective: str, plan: list[str]) -> ExecutionState:
        plan = [p.strip() for p in plan if p.strip()]
        if not objective.strip() or not plan:
            raise ValueError("an objective and at least one plan step are required")
        state = ExecutionState(task_id=f"task-{uuid.uuid4().hex[:8]}",
                               objective=objective.strip(), plan=plan)
        self.store.create(state)
        return state

    def step(self, task_id: str) -> TurnResult | None:
        """Exactly one worker turn, or None if the task is already finished."""
        state = self.store.load_state(task_id)
        if state is None:
            raise KeyError(f"unknown task {task_id!r}")
        if state.turn >= len(state.plan):
            return None

        index = state.turn
        task = state.plan[index]
        worker = self.worker_for(index)
        package = self.compiler.compile(state, task, worker.id)
        claims, raw = UniversalWorker(worker, self.gateway).run(package)

        report = self.reconciler.reconcile(state, claims, worker.id, task, worker.model)
        state.status = "completed" if state.turn >= len(state.plan) else "running"
        self.store.save_turn(state, package, raw, report, worker)

        result = TurnResult(state.turn, worker, task, package, report, state)
        if self.on_turn:
            self.on_turn(result)
        return result

    def run(self, task_id: str, max_turns: int | None = None) -> RunSummary:
        """Run until the plan is done (or ``max_turns``). Also how resume works."""
        done = 0
        while max_turns is None or done < max_turns:
            if self.step(task_id) is None:
                break
            done += 1
        return self.summary(task_id)

    def summary(self, task_id: str) -> RunSummary:
        state = self.store.load_state(task_id)
        if state is None:
            raise KeyError(f"unknown task {task_id!r}")
        turns = self.store.turns(task_id)
        return RunSummary(
            task_id=task_id,
            status=state.status,
            turns=state.turn,
            steps=len(state.plan),
            workers_used=list(dict.fromkeys(t["worker_id"] for t in turns)),
            raw_conversation_transfers=count_transfers(turns),
            peak_package_tokens=max((t["package_tokens"] for t in turns), default=0),
        )


def count_transfers(turns: list[dict]) -> int:
    """Briefings that contain an earlier worker's raw reply, verbatim.

    Measured from what was actually sent and stored, not assumed.
    """
    transfers = 0
    for i, turn in enumerate(turns):
        for earlier in turns[:i]:
            raw = earlier["raw_output"].strip()
            if len(raw) >= TRANSFER_MIN_CHARS and raw in turn["package_text"]:
                transfers += 1
    return transfers
