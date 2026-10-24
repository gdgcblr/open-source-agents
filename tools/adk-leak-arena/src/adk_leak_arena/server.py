"""FastAPI backend serving the ADK Leak Arena Red-Team Console and evaluation APIs."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

import adk_memshield
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, field_validator

from . import __version__
from .config import ArenaConfig
from .dataset import (
    ALL_PRESETS,
    ATTACK_PRESETS,
    BASELINE_SEED_SIZE,
    CALLER_PERSONAS,
    CONTROL_QUERIES,
    INJECTOR_PERSONAS,
    PRESET_BY_ID,
    S6_FIXTURE_RECORDS,
    SEED_RECORDS,
    TENANTS,
    canary_tokens,
)
from .evaluator import ATTACK_IDS, SCENARIO_IDS
from .injector import inject_memory
from .jobs import BenchmarkJobManager, BenchmarkParams, JobConflict, RunHistory
from .runner_pair import (
    EngineMode,
    check_ollama_status,
    ensure_schema_and_seed,
    probe_db_security_posture,
    run_side_by_side_comparison,
)
from .scale import SEED_SIZE_OPTIONS, TOP_K_OPTIONS, apply_seed_size, current_seed_size
from .unprotected_service import FailureMode

logger = logging.getLogger(__name__)

_STATIC_INDEX = Path(__file__).resolve().parent / "static" / "index.html"
_INITIALIZED = False

_MAX_QUERY_CHARS = 2000
_MAX_INJECT_CHARS = 1000
_IDENTIFIER_PATTERN = r"^[A-Za-z0-9_.\-]{1,64}$"
_CANARY_PATTERN = r"^[A-Za-z0-9_.$\-]{3,40}$"


def _safe_text(value: Any) -> str:
    return str(value).encode("utf-8", "backslashreplace").decode("utf-8")


def _reject_unencodable(value: str) -> str:
    # NUL bytes cannot be stored in PostgreSQL text and lone UTF-16 surrogates cannot be
    # UTF-8 encoded for the tokenizer; reject both as a clean 422 instead of a 500.
    if "\x00" in value:
        raise ValueError("NUL (0x00) characters are not allowed")
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise ValueError("unpaired UTF-16 surrogate characters are not allowed")
    return value


def _validate_caller(value: str) -> str:
    if value not in CALLER_PERSONAS:
        raise ValueError(f"unknown caller_id; expected one of {sorted(CALLER_PERSONAS)}")
    return value


def _validate_seed_size(value: int) -> int:
    if value not in SEED_SIZE_OPTIONS:
        raise ValueError(f"seed_size must be one of {list(SEED_SIZE_OPTIONS)}")
    return value


class AttackRequest(BaseModel):
    """Request body for `/api/attack` side-by-side ADK Runner execution."""

    preset_id: str | None = Field(default="S1", max_length=32)
    query: str | None = Field(default=None, max_length=_MAX_QUERY_CHARS)
    caller_id: str = Field(default="alice_analyst")
    failure_mode: FailureMode | None = Field(default=None)
    simulate_missing_app_filter: bool = Field(default=False)
    spoofed_user_id: str | None = Field(default=None, pattern=_IDENTIFIER_PATTERN)
    engine: EngineMode = Field(default="deterministic_agent")
    top_k: int = Field(default=3, ge=1, le=20)

    check_caller = field_validator("caller_id")(_validate_caller)

    @field_validator("query")
    @classmethod
    def check_query(cls, value: str | None) -> str | None:
        return _reject_unencodable(value) if value is not None else None


class BenchmarkRequest(BaseModel):
    """Request body for `/api/benchmark` and `/api/benchmark/start`."""

    caller_id: str = Field(default="alice_analyst")
    engine: EngineMode = Field(default="deterministic_agent")
    repeats: int = Field(default=3, ge=1, le=10)
    top_k: int = Field(default=3, ge=1, le=20)
    seed_size: int = Field(default=BASELINE_SEED_SIZE)
    scenarios: list[str] = Field(default_factory=lambda: list(SCENARIO_IDS), min_length=1)
    label: str = Field(default="manual", pattern=r"^[A-Za-z0-9 _.\-]{1,40}$")

    check_caller = field_validator("caller_id")(_validate_caller)
    check_seed = field_validator("seed_size")(_validate_seed_size)

    @field_validator("scenarios")
    @classmethod
    def check_scenarios(cls, value: list[str]) -> list[str]:
        unknown = [s for s in value if s not in SCENARIO_IDS]
        if unknown:
            raise ValueError(f"unknown scenarios {unknown}; expected a subset of {list(SCENARIO_IDS)}")
        return [s for s in SCENARIO_IDS if s in value]

    def to_params(self) -> BenchmarkParams:
        return BenchmarkParams(
            caller_id=self.caller_id,
            engine=self.engine,
            top_k=self.top_k,
            seed_size=self.seed_size,
            scenarios=tuple(self.scenarios),
            repeats=self.repeats,
            label=self.label,
        )


class InjectRequest(BaseModel):
    """Request body for `/api/inject` (Red-Team CTF Memory Injector)."""

    acting_persona: str = Field(default="mallory_contractor")
    claimed_owner_id: str | None = Field(default=None, pattern=_IDENTIFIER_PATTERN)
    scope: Literal["private", "tenant_shared"] = Field(default="private")
    min_clearance: int = Field(default=1, ge=1, le=5)
    content: str = Field(min_length=1, max_length=_MAX_INJECT_CHARS)
    canary_token: str | None = Field(default=None, pattern=_CANARY_PATTERN)

    @field_validator("acting_persona")
    @classmethod
    def check_actor(cls, value: str) -> str:
        if value not in INJECTOR_PERSONAS:
            raise ValueError(f"unknown acting_persona; expected one of {sorted(INJECTOR_PERSONAS)}")
        return value

    @field_validator("content")
    @classmethod
    def check_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return _reject_unencodable(value)


class ScaleRequest(BaseModel):
    seed_size: int

    check_seed = field_validator("seed_size")(_validate_seed_size)


def _history_markdown(run: dict[str, Any]) -> str:
    header = (
        f"### adk-leak-arena run {run['run_id']} ({run['status']})\n\n"
        f"- label: {run['label']} · timestamp: {run['timestamp']}\n"
        f"- engine: {run['engine']} · top_k: {run['top_k']} · seed_size: {run['seed_size']} · "
        f"repeats: {run['repeats']} · caller: {run['caller_id']}\n"
        f"- duration: {run['duration_ms']} ms · steps: {run['steps_completed']}/{run['total_steps']}\n\n"
    )
    return header + (run.get("markdown_table") or "_no completed scenarios_") + "\n"


def create_app(config: ArenaConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    cfg = config or ArenaConfig()
    seed_lock = asyncio.Lock()
    history = RunHistory()
    jobs = BenchmarkJobManager(cfg, history)

    async def _ensure_seeded() -> None:
        global _INITIALIZED
        if _INITIALIZED:
            return
        async with seed_lock:
            if not _INITIALIZED:
                await asyncio.to_thread(ensure_schema_and_seed, cfg)
                _INITIALIZED = True

    def _reject_if_running(action: str) -> None:
        if jobs.running:
            raise HTTPException(
                status_code=409,
                detail=f"cannot {action} while benchmark {jobs.job.job_id} is running; kill it first",  # type: ignore[union-attr]
            )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await _ensure_seeded()
        if cfg.startup_baseline:
            # Reference run so Run History is useful immediately; DB is already freshly seeded.
            jobs.start(BenchmarkParams(label="startup-baseline"), pre_cleanup=False)
        yield
        if jobs.running and jobs.job and jobs.job.task:
            jobs.job.task.cancel()
            await asyncio.wait({jobs.job.task}, timeout=5)

    app = FastAPI(
        title="adk-leak-arena",
        version=__version__,
        description="Red-Team Evaluation & Live SQL/RLS Telemetry Console for Google ADK Memory",
        lifespan=lifespan,
    )

    @app.exception_handler(RequestValidationError)
    async def _invalid_request(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default handler echoes the offending `input` back, which itself fails to
        # UTF-8 encode for lone surrogates; report location and message only.
        errors = [
            {"loc": list(err.get("loc", ())), "msg": _safe_text(err.get("msg", "")), "type": err.get("type")}
            for err in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled arena error")
        return JSONResponse(
            status_code=500,
            content={"error": type(exc).__name__, "detail": _safe_text(str(exc))[:500]},
        )

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(content=_STATIC_INDEX.read_text(encoding="utf-8"))

    @app.get("/api/state")
    async def get_state() -> dict[str, Any]:
        await _ensure_seeded()
        ollama, posture = await asyncio.gather(
            asyncio.to_thread(check_ollama_status, cfg),
            asyncio.to_thread(probe_db_security_posture, cfg),
        )
        return {
            "arena_version": __version__,
            "memshield_version": getattr(adk_memshield, "__version__", "unknown"),
            "app_name": cfg.app_name,
            "top_k": cfg.top_k,
            "top_k_options": list(TOP_K_OPTIONS),
            "seed_size_options": list(SEED_SIZE_OPTIONS),
            "baseline_seed_size": BASELINE_SEED_SIZE,
            "current_seed_size": current_seed_size(),
            "embedding_model": cfg.embedding_model,
            "default_engine": "deterministic_agent",
            "engines": {
                "deterministic_agent": {"available": True},
                "ollama_gemma": {
                    "available": bool(ollama["online"] and ollama["model_available"]),
                    "model": cfg.ollama_model,
                },
                "gemini_api": {"available": bool(cfg.gemini_api_key), "model": cfg.gemini_model},
            },
            "ollama": ollama,
            "gemini_available": bool(cfg.gemini_api_key),
            "db_posture": posture,
            "tenants": list(TENANTS),
            "canary_tokens": list(canary_tokens()),
            "personas": [asdict(p) for p in CALLER_PERSONAS.values()],
            "injector_personas": [asdict(p) for p in INJECTOR_PERSONAS.values()],
            "presets": [asdict(p) for p in ALL_PRESETS],
            "attack_ids": list(ATTACK_IDS),
            "scenario_ids": list(SCENARIO_IDS),
            "control_queries": [asdict(q) for q in CONTROL_QUERIES],
            "seed_records": [asdict(r) for r in SEED_RECORDS],
            "s6_fixture_records": [asdict(r) for r in S6_FIXTURE_RECORDS],
            "benchmark": jobs.status(since=10**9),
        }

    @app.post("/api/reset")
    async def reset_database() -> dict[str, Any]:
        global _INITIALIZED
        _reject_if_running("reset the database")
        async with seed_lock:
            res = await asyncio.to_thread(ensure_schema_and_seed, cfg)
            _INITIALIZED = True
        return res

    @app.post("/api/scale")
    async def scale_database(req: ScaleRequest) -> dict[str, Any]:
        _reject_if_running("rescale the database")
        await _ensure_seeded()
        async with seed_lock:
            return await asyncio.to_thread(apply_seed_size, cfg, req.seed_size)

    @app.post("/api/attack")
    async def execute_attack(req: AttackRequest) -> dict[str, Any]:
        await _ensure_seeded()
        preset = PRESET_BY_ID.get(req.preset_id or "S1", ATTACK_PRESETS[0])
        query_text = (req.query or "").strip() or preset.default_query

        result = await run_side_by_side_comparison(
            config=cfg,
            query=query_text,
            caller_id=req.caller_id,
            preset_id=req.preset_id,
            failure_mode=req.failure_mode,
            simulate_missing_app_filter=req.simulate_missing_app_filter,
            spoofed_user_id=req.spoofed_user_id,
            engine=req.engine,
            top_k=req.top_k,
        )
        result["seed_size"] = current_seed_size()
        result["benchmark_running"] = jobs.running
        result["canary_tokens"] = list(canary_tokens())
        return result

    @app.post("/api/inject")
    async def inject(req: InjectRequest) -> dict[str, Any]:
        _reject_if_running("inject memories")
        await _ensure_seeded()
        result = await inject_memory(
            cfg,
            acting_persona=req.acting_persona,
            claimed_owner_id=req.claimed_owner_id,
            scope=req.scope,
            min_clearance=req.min_clearance,
            content=req.content,
            canary_token=req.canary_token,
        )
        result["canary_tokens"] = list(canary_tokens())
        return result

    @app.post("/api/benchmark/start")
    async def start_benchmark(req: BenchmarkRequest | None = None) -> dict[str, Any]:
        await _ensure_seeded()
        try:
            job = jobs.start((req or BenchmarkRequest()).to_params())
        except JobConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return jobs.status() | {"job_id": job.job_id}

    @app.get("/api/benchmark/status")
    async def benchmark_status(since: int = 0) -> dict[str, Any]:
        return jobs.status(since=max(0, since))

    @app.post("/api/benchmark/kill")
    async def kill_benchmark() -> dict[str, Any]:
        return await jobs.kill()

    @app.post("/api/benchmark")
    async def execute_benchmark(req: BenchmarkRequest | None = None) -> dict[str, Any]:
        """Synchronous convenience wrapper: runs a job and waits for its report."""
        await _ensure_seeded()
        try:
            job = jobs.start((req or BenchmarkRequest()).to_params())
        except JobConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        assert job.task is not None
        await asyncio.shield(job.task)
        if job.status != "completed" or job.result is None:
            raise HTTPException(status_code=500, detail=job.error or f"benchmark {job.status}")
        return job.result | {"run_id": job.job_id, "cleanup": job.cleanup}

    @app.get("/api/history")
    async def list_history() -> dict[str, Any]:
        return {"runs": history.list()}

    @app.delete("/api/history")
    async def clear_history() -> dict[str, Any]:
        return {"cleared": history.clear()}

    @app.get("/api/history/{run_id}", response_model=None)
    async def get_history(run_id: str, format: Literal["json", "md"] = "json") -> Any:
        run = history.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"unknown run_id {run_id}")
        if format == "md":
            return PlainTextResponse(_history_markdown(run), media_type="text/markdown")
        return JSONResponse(json.loads(json.dumps(run)))

    return app


app = create_app()
