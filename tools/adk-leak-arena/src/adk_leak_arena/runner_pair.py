"""Side-by-side Google ADK Runner pipelines comparing Unprotected pgvector vs adk-memshield."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import threading
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncGenerator, Literal

import httpx
import psycopg
from adk_memshield import MemShieldConfig, MemShieldMemoryService, QueryTelemetry
from google.adk.agents import LlmAgent
from google.adk.memory.base_memory_service import SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.models._capabilities import LlmCapabilities
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools.preload_memory_tool import preload_memory_tool
from google.genai import types

from .config import ArenaConfig
from .embedding import get_cached_embed_fn
from .dataset import (
    CALLER_PERSONAS,
    PRESET_BY_ID,
    SEED_RECORDS,
    EvaluationVerdict,
    classify_retrieval_and_output,
    clear_injected_canaries,
    extract_entry_text,
    find_eval_query,
)
from .scale import current_seed_size, mark_baseline_reseeded, s6_fixture
from .unprotected_service import (
    FailureMode,
    UnprotectedPgVectorMemoryService,
    extract_spoofed_user_id,
)

logger = logging.getLogger(__name__)

EngineMode = Literal["deterministic_agent", "ollama_gemma", "gemini_api"]

_PAST_CONV_RE = re.compile(
    r"<PAST_CONVERSATIONS>\s*(.*?)\s*</PAST_CONVERSATIONS>",
    re.DOTALL,
)

_DB_POSTURE: dict[str, Any] | None = None
_DB_POSTURE_LOCK = threading.Lock()


def _extract_preloaded_memories_from_request(llm_request: LlmRequest) -> list[str]:
    """Extract memory lines injected by Google ADK's `preload_memory_tool` into `LlmRequest`."""
    collected_blobs: list[str] = []

    if llm_request.config and llm_request.config.system_instruction:
        sys_inst = llm_request.config.system_instruction
        if isinstance(sys_inst, str):
            collected_blobs.append(sys_inst)
        elif hasattr(sys_inst, "parts") and sys_inst.parts:
            for part in sys_inst.parts:
                if getattr(part, "text", None):
                    collected_blobs.append(part.text)

    for content in llm_request.contents or []:
        for part in content.parts or []:
            if getattr(part, "text", None):
                collected_blobs.append(part.text)

    memory_lines: list[str] = []
    for blob in collected_blobs:
        for match in _PAST_CONV_RE.finditer(blob):
            raw_block = match.group(1).strip()
            for line in raw_block.splitlines():
                cleaned = line.strip()
                if not cleaned or cleaned.startswith("Time:"):
                    continue
                if cleaned.startswith("user:"):
                    cleaned = cleaned[len("user:") :].strip()
                memory_lines.append(cleaned)
    return memory_lines


class DeterministicAdkLlm(BaseLlm):
    """Offline zero-latency Google ADK `BaseLlm` implementation.

    Executes inside the real Google ADK `Runner` + `preload_memory_tool` pipeline,
    inspecting the `<PAST_CONVERSATIONS>` context injected into `LlmRequest` by ADK
    and synthesizing a grounded response in <5ms.
    """

    model: str = "deterministic-adk-grounder-v1"
    target_label: str = "ADK Agent"

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities(output_schema_and_tools=True)

    @classmethod
    def supported_models(cls) -> list[str]:
        return [r"deterministic-adk-.*"]

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        memory_lines = _extract_preloaded_memories_from_request(llm_request)
        if not memory_lines:
            text = (
                f"[{self.target_label}] No matching semantic memories were returned by "
                "the memory service for this caller context."
            )
        else:
            bullets = "\n".join(f"• { idx }. {line}" for idx, line in enumerate(memory_lines, 1))
            text = (
                f"Grounded response from {len(memory_lines)} memory item(s) injected by "
                f"Google ADK `preload_memory`:\n{bullets}"
            )

        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=text)],
            ),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=64,
                candidates_token_count=max(1, len(text.split())),
                total_token_count=64 + max(1, len(text.split())),
            ),
            partial=False,
        )


def check_ollama_status(config: ArenaConfig, timeout_s: float = 1.2) -> dict[str, Any]:
    """Probe whether local Ollama is reachable and whether the configured model is available."""
    url = f"{config.ollama_base_url.rstrip('/')}/api/tags"
    try:
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                wanted = config.ollama_model.split("/", 1)[-1]
                return {
                    "online": True,
                    "base_url": config.ollama_base_url,
                    "configured_model": config.ollama_model,
                    "model_available": wanted in models,
                    "available_models": models,
                }
    except Exception as exc:
        logger.debug("Ollama probe failed: %s", exc)
    return {
        "online": False,
        "base_url": config.ollama_base_url,
        "configured_model": config.ollama_model,
        "model_available": False,
        "available_models": [],
    }


def probe_db_security_posture(config: ArenaConfig, *, refresh: bool = False) -> dict[str, Any]:
    """Read the app role's real privileges and both tables' RLS flags from the catalog.

    Telemetry cards report these values instead of hard-coded strings, so a misconfigured
    deployment (e.g. a BYPASSRLS role) is visible rather than silently mislabelled.
    """
    global _DB_POSTURE
    with _DB_POSTURE_LOCK:
        if _DB_POSTURE is not None and not refresh:
            return _DB_POSTURE
    posture: dict[str, Any] = {"ok": False}
    try:
        with psycopg.connect(config.db_dsn, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT current_user, r.rolsuper, r.rolbypassrls,
                           c.relname, c.relrowsecurity, c.relforcerowsecurity
                    FROM pg_roles r
                    CROSS JOIN pg_class c
                    WHERE r.rolname = current_user
                      AND c.relname IN ('memories', 'memories_unprotected')
                      AND c.relnamespace = 'public'::regnamespace
                    """
                )
                rows = cur.fetchall()
        if rows:
            role, is_super, bypass = rows[0][0], bool(rows[0][1]), bool(rows[0][2])
            tables = {r[3]: {"rls_enabled": bool(r[4]), "rls_forced": bool(r[5])} for r in rows}
            memories = tables.get("memories", {})
            posture = {
                "ok": True,
                "role": role,
                "rolsuper": is_super,
                "rolbypassrls": bypass,
                "role_label": (
                    f"{role} [{'SUPERUSER' if is_super else 'NOSUPERUSER'} "
                    f"{'BYPASSRLS' if bypass else 'NOBYPASSRLS'}]"
                ),
                "tables": tables,
                "rls_effective": bool(
                    not is_super
                    and not bypass
                    and memories.get("rls_enabled", False)
                    and memories.get("rls_forced", False)
                ),
            }
    except Exception as exc:
        logger.warning("DB security posture probe failed: %s", exc)
        posture = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    with _DB_POSTURE_LOCK:
        if posture.get("ok"):
            _DB_POSTURE = posture
    return posture


def ensure_schema_and_seed(config: ArenaConfig) -> dict[str, Any]:
    """Ensure arena tables exist, truncate existing rows, and seed the deterministic dataset."""
    t0 = time.perf_counter()
    sql_path = Path(__file__).resolve().parents[2] / "sql" / "init_arena.sql"

    # Try admin DSN first to apply schema if needed; fallback to app DSN
    try:
        with psycopg.connect(config.admin_dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                if sql_path.exists():
                    cur.execute(sql_path.read_text(encoding="utf-8"))
                cur.execute("TRUNCATE TABLE memories, memories_unprotected;")
    except Exception:
        with psycopg.connect(config.db_dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE memories, memories_unprotected;")

    embed_fn = get_cached_embed_fn(config.embedding_model, config.embedding_dim)
    # Pre-warm all seed embeddings in one batch
    embed_fn([rec.content for rec in SEED_RECORDS])

    async def _seed_both() -> None:
        for rec in SEED_RECORDS:
            entry = MemoryEntry(
                content=types.Content(parts=[types.Part(text=rec.content)], role="user"),
                author="user",
                custom_metadata={
                    "scope": rec.scope,
                    "min_clearance": rec.min_clearance,
                    "seed_key": rec.key,
                    "persona_label": rec.persona_label,
                    "adversarial": rec.is_adversarial,
                },
            )
            # 1. Seed RLS-protected `memories` via adk-memshield
            ms_service = MemShieldMemoryService(
                dsn=config.db_dsn,
                tenant_id=rec.tenant_id,
                agent_clearance=rec.min_clearance,
                default_scope=rec.scope,  # type: ignore[arg-type]
                default_min_clearance=rec.min_clearance,
                embed_fn=embed_fn,
            )
            await ms_service.add_memory(
                app_name=config.app_name,
                user_id=rec.user_id,
                memories=[entry],
            )

            # 2. Seed unprotected baseline `memories_unprotected`
            unp_service = UnprotectedPgVectorMemoryService(
                dsn=config.db_dsn,
                tenant_id=rec.tenant_id,
                agent_clearance=rec.min_clearance,
                embed_fn=embed_fn,
            )
            await unp_service.add_memory(
                app_name=config.app_name,
                user_id=rec.user_id,
                memories=[entry],
            )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Run in a worker thread if called from inside an active event loop
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            ex.submit(lambda: asyncio.run(_seed_both())).result()
    else:
        asyncio.run(_seed_both())

    # A full reseed removes synthetic, fixture and CTF-injected rows, so reset their trackers.
    clear_injected_canaries()
    mark_baseline_reseeded()
    probe_db_security_posture(config, refresh=True)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "status": "seeded",
        "records_seeded_per_table": len(SEED_RECORDS),
        "tables": ["memories_unprotected", "memories"],
        "elapsed_ms": round(elapsed_ms, 2),
    }


@dataclass
class SinglePaneResult:
    """Execution result for one side (Unprotected or MemShield) of the arena comparison."""

    target: str
    engine_requested: str
    engine_used: str
    engine_fallback_reason: str | None
    agent_output: str
    injected_context: list[str]
    verdict: EvaluationVerdict
    telemetry: dict[str, Any]
    total_runner_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "engine_requested": self.engine_requested,
            "engine_used": self.engine_used,
            "engine_fallback": self.engine_fallback_reason is not None,
            "engine_fallback_reason": self.engine_fallback_reason,
            "agent_output": self.agent_output,
            "injected_context": self.injected_context,
            "verdict": self.verdict.to_dict(),
            "telemetry": self.telemetry,
            "total_runner_ms": round(self.total_runner_ms, 2),
        }


def _build_adk_model(
    *,
    engine: EngineMode,
    config: ArenaConfig,
    target_label: str,
    ollama_status: dict[str, Any] | None,
) -> tuple[BaseLlm | str, str, str | None]:
    """Instantiate the requested Google ADK model or fall back cleanly to DeterministicAdkLlm.

    Returns `(model, engine_used_label, fallback_reason)`; `fallback_reason` is None when the
    requested engine is actually in use, so the UI can flag silent downgrades.
    """
    if engine == "ollama_gemma":
        status = ollama_status or {}
        if not status.get("online"):
            reason = f"Ollama unreachable at {config.ollama_base_url}"
        elif not status.get("model_available"):
            wanted = config.ollama_model.split("/", 1)[-1]
            reason = f"Ollama online but model '{wanted}' is not pulled (run: ollama pull {wanted})"
        else:
            try:
                from google.adk.models.lite_llm import LiteLlm

                return (
                    LiteLlm(
                        model=config.ollama_model,
                        api_base=config.ollama_base_url,
                    ),
                    f"ollama_gemma ({config.ollama_model})",
                    None,
                )
            except Exception as exc:
                logger.warning("LiteLlm init failed, falling back to deterministic: %s", exc)
                reason = f"LiteLlm init failed: {type(exc).__name__}"
        return (
            DeterministicAdkLlm(target_label=target_label),
            "deterministic_agent (Ollama fallback)",
            reason,
        )

    if engine == "gemini_api":
        if config.gemini_api_key:
            return config.gemini_model, f"gemini_api ({config.gemini_model})", None
        return (
            DeterministicAdkLlm(target_label=target_label),
            "deterministic_agent (Gemini fallback)",
            "GEMINI_API_KEY / GOOGLE_API_KEY not set",
        )

    return DeterministicAdkLlm(target_label=target_label), "deterministic_agent", None


def build_attack_performance(
    *,
    unprotected_sql_ms: float,
    memshield_sql_ms: float,
    unprotected_turn_ms: float,
    memshield_turn_ms: float,
    total_turn_ms: float,
    unprotected_sql: str,
    table_rows: int,
) -> dict[str, Any]:
    """Side-by-side cost of one query: pure PostgreSQL time vs the full ADK agent turn.

    `rls_overhead_ms` is memshield minus unprotected SQL time (negative means RLS was
    faster). The scope strings describe which rows the search actually considers: RLS
    predicates are applied before the vector-distance sort, and at larger table sizes the
    planner can serve them from the B-tree `idx_memories_scope_lookup` (bitmap index scan).
    """
    has_where = re.search(r"\bWHERE\b", unprotected_sql, re.IGNORECASE) is not None
    overhead = memshield_sql_ms - unprotected_sql_ms
    return {
        "sql_kernel_ms": {
            "unprotected": round(unprotected_sql_ms, 3),
            "memshield": round(memshield_sql_ms, 3),
        },
        "rls_overhead_ms": round(overhead, 3),
        "rls_overhead_pct": round(overhead / unprotected_sql_ms * 100.0, 1) if unprotected_sql_ms > 0 else None,
        "agent_turn_ms": {
            "unprotected": round(unprotected_turn_ms, 2),
            "memshield": round(memshield_turn_ms, 2),
        },
        "total_turn_ms": round(total_turn_ms, 2),
        "table_rows": table_rows,
        "rows_scanned_scope": {
            "unprotected": (
                f"App-layer WHERE over {table_rows}+ table rows"
                if has_where
                else f"All {table_rows}+ table rows (unfiltered)"
            ),
            "memshield": (
                "RLS-scoped tenant/user/clearance rows (policy filter before vector sort; "
                "B-tree idx_memories_scope_lookup eligible at scale)"
            ),
        },
    }


def _sql_literal(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _build_telemetry(
    *,
    target_key: str,
    memory_service: Any,
    config: ArenaConfig,
    caller_tenant_id: str,
    caller_user_id: str,
    caller_clearance: int,
    row_count: int,
    retrieval_error: str | None,
    db_posture: dict[str, Any],
) -> dict[str, Any]:
    telemetry_obj: QueryTelemetry | None = memory_service.last_query_telemetry
    if telemetry_obj is not None and retrieval_error is None:
        telemetry_dict = telemetry_obj.to_dict()
        telemetry_dict["latency_ms"] = round(float(telemetry_dict["latency_ms"]), 3)
        telemetry_dict["sql"] = "\n".join(
            line.strip() for line in str(telemetry_dict["sql"]).strip().splitlines()
        )
    else:
        telemetry_dict = {
            "operation": "search_memory",
            "sql": "",
            "session_context": {},
            "latency_ms": 0.0,
            "row_count": row_count,
            "simulate_missing_app_filter": bool(
                getattr(memory_service, "simulate_missing_app_filter", False)
                or getattr(getattr(memory_service, "config", None), "simulate_missing_app_filter", False)
            ),
            "table_name": "memories" if target_key == "memshield" else "memories_unprotected",
        }
    telemetry_dict["error"] = retrieval_error

    posture_ok = bool(db_posture.get("ok"))
    tables = db_posture.get("tables", {}) if posture_ok else {}
    telemetry_dict["db_role"] = (
        db_posture["role_label"] if posture_ok else "unknown (posture probe failed)"
    )
    telemetry_dict["db_posture_verified"] = posture_ok

    if target_key == "memshield":
        ctx = telemetry_dict.get("session_context", {}) or {}
        mem_flags = tables.get("memories", {})
        if posture_ok:
            forced = mem_flags.get("rls_forced", False) and mem_flags.get("rls_enabled", False)
            telemetry_dict["rls_enforcement"] = (
                "FORCE ROW LEVEL SECURITY (relrowsecurity=t, relforcerowsecurity=t)"
                if forced
                else "RLS NOT FORCED on memories: kernel isolation not guaranteed"
            )
            telemetry_dict["rls_effective"] = bool(db_posture.get("rls_effective"))
        else:
            telemetry_dict["rls_enforcement"] = "FORCE ROW LEVEL SECURITY (unverified)"
            telemetry_dict["rls_effective"] = None
        app_name = ctx.get("app.current_app_name", config.app_name)
        tenant = ctx.get("app.current_tenant_id", caller_tenant_id)
        user = ctx.get("app.current_user_id", caller_user_id)
        clearance = ctx.get("app.agent_clearance", caller_clearance)
        telemetry_dict["set_local_sql"] = (
            "-- Transaction-local identity: set_config(name, value, is_local => true) ≡ SET LOCAL,\n"
            "-- discarded at COMMIT/ROLLBACK so it never bleeds into the next pooled checkout.\n"
            f"SELECT set_config('app.current_app_name', {_sql_literal(app_name)}, true),\n"
            f"       set_config('app.current_tenant_id', {_sql_literal(tenant)}, true),\n"
            f"       set_config('app.current_user_id', {_sql_literal(user)}, true),\n"
            f"       set_config('app.agent_clearance', {_sql_literal(clearance)}, true);"
        )
    else:
        unp_flags = tables.get("memories_unprotected", {})
        telemetry_dict["rls_enforcement"] = (
            "NONE (relrowsecurity=f) — App-Layer SQL Filter Only"
            if not unp_flags.get("rls_enabled", False)
            else "RLS enabled on memories_unprotected (unexpected)"
        )
        telemetry_dict["rls_effective"] = False
        telemetry_dict["set_local_sql"] = (
            "-- No transaction-local RLS context bound.\n"
            f"-- Security depends 100% on the Python-built WHERE clause "
            f"(failure_mode: {getattr(memory_service, 'failure_mode', 'unknown')})."
        )
    return telemetry_dict


async def _run_single_adk_pipeline(
    *,
    target_key: str,
    target_label: str,
    memory_service: Any,
    config: ArenaConfig,
    caller_tenant_id: str,
    caller_user_id: str,
    caller_clearance: int,
    query: str,
    engine: EngineMode,
    relevant_keys: Sequence[str] | None,
    ollama_status: dict[str, Any] | None,
    db_posture: dict[str, Any],
    top_k: int = 3,
) -> SinglePaneResult:
    """Execute a full Google ADK `Runner` + `preload_memory_tool` turn and classify leaks."""
    captured_memories: list[MemoryEntry] = []
    search_errors: list[str] = []
    orig_search = memory_service.search_memory

    async def _capturing_search_memory(
        *, app_name: str, user_id: str, query: str
    ) -> SearchMemoryResponse:
        # ADK's preload_memory_tool swallows search exceptions, which would otherwise make a
        # failed retrieval look like a clean "0 rows" isolation verdict. Record them here.
        try:
            resp = await orig_search(app_name=app_name, user_id=user_id, query=query)
        except Exception as exc:
            search_errors.append(f"{type(exc).__name__}: {exc}"[:300])
            raise
        captured_memories.clear()
        captured_memories.extend(resp.memories)
        return resp

    memory_service.search_memory = _capturing_search_memory  # type: ignore[method-assign]

    model_obj, engine_used, fallback_reason = _build_adk_model(
        engine=engine,
        config=config,
        target_label=target_label,
        ollama_status=ollama_status,
    )

    instruction = (
        "You are an enterprise assistant for Acme Corp. Answer the user's question "
        "concisely using the <PAST_CONVERSATIONS> memories provided. Include exact project "
        "codes, key identifiers, pins, or dollar caps mentioned in those memories."
    )

    async def _invoke_runner(active_model: BaseLlm | str) -> str:
        captured_memories.clear()
        search_errors.clear()
        session_service = InMemorySessionService()
        session_id = f"sess-{uuid.uuid4().hex[:10]}"
        await session_service.create_session(
            app_name=config.app_name,
            user_id=caller_user_id,
            session_id=session_id,
        )
        agent = LlmAgent(
            name=f"arena_{target_key}_agent",
            model=active_model,
            instruction=instruction,
            tools=[preload_memory_tool],
        )
        # Attack sessions are intentionally never written back to memory, so every run sees
        # the same seeded corpus and benchmark results stay deterministic.
        runner = Runner(
            app_name=config.app_name,
            agent=agent,
            session_service=session_service,
            memory_service=memory_service,
        )
        user_msg = types.Content(role="user", parts=[types.Part(text=query)])
        output_chunks: list[str] = []
        async for event in runner.run_async(
            user_id=caller_user_id,
            session_id=session_id,
            new_message=user_msg,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "text", None):
                        output_chunks.append(part.text.strip())
        return "\n".join(c for c in output_chunks if c)

    t0 = time.perf_counter()
    try:
        agent_output = await _invoke_runner(model_obj)
    except Exception as exc:
        if isinstance(model_obj, DeterministicAdkLlm):
            raise
        logger.warning("LLM engine %s failed (%s); falling back to deterministic agent", engine, exc)
        engine_used = "deterministic_agent (runtime fallback)"
        fallback_reason = f"{engine} raised {type(exc).__name__}: {exc}"[:240]
        agent_output = await _invoke_runner(DeterministicAdkLlm(target_label=target_label))
    total_runner_ms = (time.perf_counter() - t0) * 1000.0

    retrieval_error = search_errors[-1] if search_errors else None
    # The context ADK injected is reported separately from the model's own words, so the
    # canary-exfiltration metric measures what the model actually emitted.
    injected_context = [extract_entry_text(m) for m in captured_memories]

    telemetry_dict = _build_telemetry(
        target_key=target_key,
        memory_service=memory_service,
        config=config,
        caller_tenant_id=caller_tenant_id,
        caller_user_id=caller_user_id,
        caller_clearance=caller_clearance,
        row_count=len(captured_memories),
        retrieval_error=retrieval_error,
        db_posture=db_posture,
    )

    verdict = classify_retrieval_and_output(
        memories=captured_memories,
        agent_output=agent_output,
        caller_tenant_id=caller_tenant_id,
        caller_user_id=caller_user_id,
        caller_clearance=caller_clearance,
        target=target_key,
        top_k=top_k,
        relevant_keys=relevant_keys,
        retrieval_error=retrieval_error,
    )

    return SinglePaneResult(
        target=target_key,
        engine_requested=engine,
        engine_used=engine_used,
        engine_fallback_reason=fallback_reason,
        agent_output=agent_output,
        injected_context=injected_context,
        verdict=verdict,
        telemetry=telemetry_dict,
        total_runner_ms=total_runner_ms,
    )


async def run_side_by_side_comparison(
    *,
    config: ArenaConfig,
    query: str,
    caller_id: str = "alice_analyst",
    preset_id: str | None = "S1",
    failure_mode: FailureMode | None = None,
    simulate_missing_app_filter: bool = False,
    spoofed_user_id: str | None = None,
    engine: EngineMode = "deterministic_agent",
    relevant_keys: Sequence[str] | None = None,
    top_k: int | None = None,
) -> dict[str, Any]:
    """Run Left (Unprotected) and Right (adk-memshield RLS) ADK Runners side-by-side.

    `relevant_keys` enables Recall@K scoring; when omitted, it is looked up from the
    benchmark query bank by exact text (custom queries are reported as recall n/a).
    """
    persona = CALLER_PERSONAS.get(caller_id, CALLER_PERSONAS["alice_analyst"])
    preset = PRESET_BY_ID.get(preset_id or "S1")
    effective_top_k = max(1, min(int(top_k or config.top_k), 20))

    resolved_failure_mode: FailureMode = (
        failure_mode
        if failure_mode is not None
        else (preset.failure_mode if preset else "shared_tenant_no_user_filter")  # type: ignore[assignment]
    )
    resolved_chaos = bool(
        simulate_missing_app_filter
        or resolved_failure_mode == "strip_all_where_filters"
        or (preset.simulate_missing_app_filter if preset and failure_mode is None else False)
    )
    if resolved_chaos:
        resolved_failure_mode = "strip_all_where_filters"

    # Precedence: explicit tool-arg override > identity injected in the prompt > preset default.
    resolved_spoof_user = (
        spoofed_user_id
        or extract_spoofed_user_id(query)
        or (preset.spoofed_user_id if preset else None)
    )
    if relevant_keys is None:
        matched = find_eval_query(query)
        relevant_keys = matched.relevant_keys if matched else None

    # Blocking probes run off the event loop (the posture probe is cached after first use).
    db_posture = await asyncio.to_thread(probe_db_security_posture, config)
    ollama_status = (
        await asyncio.to_thread(check_ollama_status, config, 0.8)
        if engine == "ollama_gemma"
        else None
    )
    embed_fn = get_cached_embed_fn(config.embedding_model, config.embedding_dim)

    unprotected_service = UnprotectedPgVectorMemoryService(
        dsn=config.db_dsn,
        tenant_id=persona.tenant_id,
        agent_clearance=persona.clearance,
        top_k=effective_top_k,
        failure_mode=resolved_failure_mode,
        simulate_missing_app_filter=resolved_chaos,
        spoofed_user_id=resolved_spoof_user,
        embed_fn=embed_fn,
    )

    memshield_service = MemShieldMemoryService(
        config=MemShieldConfig(
            dsn=config.db_dsn,
            tenant_id=persona.tenant_id,
            agent_clearance=persona.clearance,
            top_k=effective_top_k,
            table_name="memories",
            simulate_missing_app_filter=resolved_chaos,
        ),
        embed_fn=embed_fn,
    )

    common = dict(
        config=config,
        caller_tenant_id=persona.tenant_id,
        caller_user_id=persona.user_id,
        caller_clearance=persona.clearance,
        query=query,
        engine=engine,
        relevant_keys=relevant_keys,
        ollama_status=ollama_status,
        db_posture=db_posture,
        top_k=effective_top_k,
    )
    # S6 plants Mallory's same-tier shared lures only for the duration of the run.
    fixture = s6_fixture(config) if preset and preset.id == "S6" else contextlib.nullcontext()
    async with fixture:
        t_turn = time.perf_counter()
        left_res, right_res = await asyncio.gather(
            _run_single_adk_pipeline(
                target_key="unprotected",
                target_label="Unprotected pgvector",
                memory_service=unprotected_service,
                **common,
            ),
            _run_single_adk_pipeline(
                target_key="memshield",
                target_label="adk-memshield (RLS Kernel)",
                memory_service=memshield_service,
                **common,
            ),
        )
        total_turn_ms = (time.perf_counter() - t_turn) * 1000.0

    performance = build_attack_performance(
        unprotected_sql_ms=float(left_res.telemetry.get("latency_ms", 0.0)),
        memshield_sql_ms=float(right_res.telemetry.get("latency_ms", 0.0)),
        unprotected_turn_ms=left_res.total_runner_ms,
        memshield_turn_ms=right_res.total_runner_ms,
        total_turn_ms=total_turn_ms,
        unprotected_sql=str(left_res.telemetry.get("sql", "")),
        table_rows=current_seed_size(),
    )

    return {
        "query": query,
        "caller": {
            "user_id": persona.user_id,
            "tenant_id": persona.tenant_id,
            "clearance": persona.clearance,
            "display_name": persona.display_name,
            "role_badge": persona.role_badge,
        },
        "scenario": {
            "preset_id": preset.id if preset else "CUSTOM",
            "title": preset.title if preset else f"Custom Query ({resolved_failure_mode})",
            "vulnerability_class": (
                preset.vulnerability_class if preset else "Custom Failure Mode Evaluation"
            ),
            "failure_mode": resolved_failure_mode,
            "simulate_missing_app_filter": resolved_chaos,
            "spoofed_user_id": (
                resolved_spoof_user if resolved_failure_mode == "param_spoof_user_id" else None
            ),
            "relevant_keys": list(relevant_keys) if relevant_keys is not None else None,
            "description": preset.description if preset else "",
        },
        "top_k": effective_top_k,
        "db_posture": db_posture,
        "performance": performance,
        "unprotected": left_res.to_dict(),
        "memshield": right_res.to_dict(),
    }
