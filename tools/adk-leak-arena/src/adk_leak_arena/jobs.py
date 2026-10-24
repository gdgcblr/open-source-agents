"""Background benchmark job runner with progress, streaming logs, kill switch and run history."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .config import ArenaConfig
from .dataset import BASELINE_SEED_SIZE
from .evaluator import SCENARIO_IDS, BenchmarkCancelled, run_full_benchmark
from .runner_pair import EngineMode, ensure_schema_and_seed
from .scale import apply_seed_size, current_seed_size, delete_synthetic

logger = logging.getLogger(__name__)

ABORT_MESSAGE = "Run aborted by operator; database restored to 36-row baseline."
_MAX_LOG_LINES = 2000
_KILL_GRACE_S = 0.1  # cooperative stop window before hard task cancellation


class JobConflict(Exception):
    """Raised when a benchmark is started while another one is still running."""


@dataclass(frozen=True)
class BenchmarkParams:
    caller_id: str = "alice_analyst"
    engine: EngineMode = "deterministic_agent"
    top_k: int = 3
    seed_size: int = BASELINE_SEED_SIZE
    scenarios: tuple[str, ...] = SCENARIO_IDS
    repeats: int = 3
    label: str = "manual"

    def as_dict(self) -> dict[str, Any]:
        return {
            "caller_id": self.caller_id,
            "engine": self.engine,
            "top_k": self.top_k,
            "seed_size": self.seed_size,
            "scenarios": list(self.scenarios),
            "repeats": self.repeats,
            "label": self.label,
        }


@dataclass
class BenchmarkJob:
    params: BenchmarkParams
    pre_cleanup: bool = True
    job_id: str = field(default_factory=lambda: f"run-{uuid.uuid4().hex[:8]}")
    status: str = "queued"  # queued | running | completed | cancelled | failed
    phase: str = "queued"  # queued | pre_cleanup | evaluating | post_cleanup | done
    created_at: float = field(default_factory=time.time)
    started_perf: float = field(default_factory=time.perf_counter)
    finished_perf: float | None = None
    step: int = 0
    total_steps: int = 0
    current: str = ""
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=_MAX_LOG_LINES))
    log_base: int = 0  # index of logs[0] in the full stream (older lines are dropped)
    result: dict[str, Any] | None = None
    error: str | None = None
    kill_requested_at: float | None = None
    abort_latency_ms: float | None = None
    cleanup: dict[str, Any] | None = None
    task: asyncio.Task[None] | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)

    def log(self, message: str) -> None:
        stamp = f"{time.perf_counter() - self.started_perf:7.2f}s"
        if len(self.logs) == self.logs.maxlen:
            self.log_base += 1
        self.logs.append(f"[{stamp}] {message}")

    def on_progress(self, step: int, total: int, label: str) -> None:
        self.step, self.total_steps, self.current = step, total, label

    @property
    def elapsed_ms(self) -> float:
        end = self.finished_perf or time.perf_counter()
        return round((end - self.started_perf) * 1000.0, 1)

    def snapshot(self, since: int = 0) -> dict[str, Any]:
        start = max(0, since - self.log_base)
        lines = list(self.logs)[start:]
        percent = round(100.0 * self.step / self.total_steps, 1) if self.total_steps else 0.0
        if self.status == "completed":
            percent = 100.0
        return {
            "job_id": self.job_id,
            "status": self.status,
            "phase": self.phase,
            "params": self.params.as_dict(),
            "step": self.step,
            "total_steps": self.total_steps,
            "percent": percent,
            "current": self.current,
            "elapsed_ms": self.elapsed_ms,
            "logs": lines,
            "log_offset": self.log_base + len(self.logs),
            "error": self.error,
            "abort_latency_ms": self.abort_latency_ms,
            "cleanup": self.cleanup,
            "result": self.result if self.status in ("completed", "cancelled") else None,
            "performance": (self.result or {}).get("performance"),
        }


class RunHistory:
    """Bounded in-memory history of completed and cancelled runs (newest first)."""

    def __init__(self, limit: int = 50) -> None:
        self._runs: deque[dict[str, Any]] = deque(maxlen=limit)

    def add(self, entry: dict[str, Any]) -> None:
        self._runs.appendleft(entry)

    def list(self) -> list[dict[str, Any]]:
        return list(self._runs)

    def get(self, run_id: str) -> dict[str, Any] | None:
        return next((r for r in self._runs if r["run_id"] == run_id), None)

    def clear(self) -> int:
        n = len(self._runs)
        self._runs.clear()
        return n


class BenchmarkJobManager:
    """Runs one benchmark at a time as an asyncio task on the server's event loop."""

    def __init__(self, config: ArenaConfig, history: RunHistory) -> None:
        self.config = config
        self.history = history
        self.job: BenchmarkJob | None = None

    @property
    def running(self) -> bool:
        return self.job is not None and self.job.status in ("queued", "running")

    def start(self, params: BenchmarkParams, *, pre_cleanup: bool = True) -> BenchmarkJob:
        if self.running:
            raise JobConflict(f"benchmark {self.job.job_id} is already running")  # type: ignore[union-attr]
        job = BenchmarkJob(params=params, pre_cleanup=pre_cleanup)
        self.job = job
        job.task = asyncio.create_task(self._execute(job), name=job.job_id)
        return job

    def status(self, since: int = 0) -> dict[str, Any]:
        if self.job is None:
            return {"status": "idle", "job_id": None, "logs": [], "log_offset": 0, "percent": 0.0}
        return self.job.snapshot(since)

    async def kill(self) -> dict[str, Any]:
        job = self.job
        if job is None or not self.running:
            return self.status()
        job.kill_requested_at = time.perf_counter()
        job.cancel_event.set()
        job.log("KILL RUN requested by operator")
        task = job.task
        if task is not None:
            # Cooperative stop first (checked between every query); hard-cancel anything still
            # in flight, such as a long LLM generation, after the grace window. Never cancel
            # the cleanup phase itself.
            done, _ = await asyncio.wait({task}, timeout=_KILL_GRACE_S)
            if not done and job.phase in ("pre_cleanup", "evaluating"):
                task.cancel()
            await asyncio.wait({task}, timeout=30)
        return self.status()

    async def _execute(self, job: BenchmarkJob) -> None:
        cfg, p = self.config, job.params
        cancelled = False
        outcome = "failed"
        job.status = "running"
        job.log(
            f"start {job.job_id} label={p.label} engine={p.engine} top_k={p.top_k} "
            f"seed_size={p.seed_size} repeats={p.repeats} scenarios={','.join(p.scenarios)}"
        )
        try:
            if job.pre_cleanup:
                job.phase = "pre_cleanup"
                job.log("pre-run cleanup: TRUNCATE + reseed 36-row baseline (clears CTF injections)")
                seeded = await asyncio.to_thread(ensure_schema_and_seed, cfg)
                job.log(f"pre-run cleanup: baseline seeded in {seeded['elapsed_ms']} ms")
            if p.seed_size > BASELINE_SEED_SIZE:
                job.phase = "pre_cleanup"
                info = await asyncio.to_thread(apply_seed_size, cfg, p.seed_size)
                job.log(
                    f"scale: {info['synthetic_rows_per_table']} synthetic rows/table via {info['method']} "
                    f"(generate {info['generate_ms']} ms, load {info['load_ms']} ms, total {info['elapsed_ms']} ms)"
                )
            if job.cancel_event.is_set():
                raise BenchmarkCancelled({})
            job.phase = "evaluating"
            job.result = await run_full_benchmark(
                cfg,
                caller_id=p.caller_id,
                engine=p.engine,
                repeats=p.repeats,
                top_k=p.top_k,
                scenarios=p.scenarios,
                progress=job.on_progress,
                log=job.log,
                cancel_event=job.cancel_event,
            )
            outcome = "completed"
            job.log(f"completed {job.step}/{job.total_steps} steps in {job.result['elapsed_ms']} ms")
        except BenchmarkCancelled as exc:
            cancelled = True
            job.result = exc.partial or None
        except asyncio.CancelledError:
            cancelled = True
        except Exception as exc:  # surfaced in status; never crash the server loop
            logger.exception("benchmark job failed")
            outcome = "failed"
            job.error = f"{type(exc).__name__}: {exc}"[:500]
            job.log(f"FAILED: {job.error}")
        if cancelled:
            outcome = "cancelled"
            if job.kill_requested_at is not None:
                job.abort_latency_ms = round((time.perf_counter() - job.kill_requested_at) * 1000.0, 1)
            job.log(f"evaluation stopped {job.abort_latency_ms} ms after KILL RUN")

        job.phase = "post_cleanup"
        try:
            t0 = time.perf_counter()
            if cancelled or outcome == "failed":
                seeded = await asyncio.to_thread(ensure_schema_and_seed, cfg)
                job.cleanup = {"action": "full_reseed", "elapsed_ms": seeded["elapsed_ms"]}
                job.log(ABORT_MESSAGE if cancelled else "database restored to 36-row baseline after failure")
            elif current_seed_size() > BASELINE_SEED_SIZE:
                removed = await asyncio.to_thread(delete_synthetic, cfg)
                job.cleanup = {
                    "action": "delete_synthetic",
                    "rows_removed": removed,
                    "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                }
                job.log(f"post-run cleanup: removed {removed} synthetic rows; back to 36-row baseline")
            else:
                job.cleanup = {"action": "none"}
        except Exception as exc:
            logger.exception("post-run cleanup failed")
            job.log(f"post-run cleanup FAILED: {type(exc).__name__}: {exc}")
        job.phase = "done"
        job.finished_perf = time.perf_counter()
        # Publish the terminal state only after cleanup, so pollers never observe a finished
        # job whose database is still being restored.
        job.status = outcome

        if job.status in ("completed", "cancelled"):
            self.history.add(self._history_entry(job))

    @staticmethod
    def _history_entry(job: BenchmarkJob) -> dict[str, Any]:
        r = job.result or {}
        return {
            "run_id": job.job_id,
            "label": job.params.label,
            "timestamp": dt.datetime.fromtimestamp(job.created_at, dt.timezone.utc).isoformat(timespec="seconds"),
            "status": job.status,
            **{k: v for k, v in job.params.as_dict().items() if k != "label"},
            "duration_ms": job.elapsed_ms,
            "steps_completed": job.step,
            "total_steps": job.total_steps,
            "abort_latency_ms": job.abort_latency_ms,
            "aggregate_attacks": r.get("aggregate_attacks"),
            "performance": r.get("performance"),
            "scenarios_detail": r.get("scenarios", []),
            "methodology": r.get("methodology"),
            "markdown_table": r.get("markdown_table", ""),
        }
