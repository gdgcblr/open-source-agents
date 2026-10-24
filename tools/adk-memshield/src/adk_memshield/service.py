"""Google ADK BaseMemoryService implementation backed by PostgreSQL pgvector + RLS."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import psycopg
from google.adk.events.event import Event
from google.adk.memory.base_memory_service import BaseMemoryService, SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.sessions.session import Session
from google.genai import types
from psycopg_pool import ConnectionPool

from .config import MemShieldConfig
from .embedder import EmbedFn, MemShieldEmbedder

_SHARED_POOLS: dict[str, ConnectionPool] = {}


def _get_shared_pool(dsn: str) -> ConnectionPool:
    """Return a process-shared ConnectionPool keyed by PostgreSQL DSN."""
    pool = _SHARED_POOLS.get(dsn)
    if pool is None or pool.closed:
        pool = ConnectionPool(conninfo=dsn, min_size=1, max_size=8, open=True)
        _SHARED_POOLS[dsn] = pool
    return pool


def _format_vector(vec: Sequence[float]) -> str:
    """Serialize a float sequence as a pgvector literal string."""
    return "[" + ",".join(f"{float(x):.8f}" for x in vec) + "]"


def _extract_text_from_content(content: types.Content | None) -> str:
    """Extract concatenated non-empty text parts from a google.genai Content object."""
    if content is None or not content.parts:
        return ""
    texts: list[str] = []
    for part in content.parts:
        if getattr(part, "text", None):
            stripped = part.text.strip()
            if stripped:
                texts.append(stripped)
    return "\n".join(texts)


def _require_identity(app_name: str, user_id: str) -> None:
    """Reject empty identities before they reach the database (fail closed)."""
    if not app_name or not str(app_name).strip():
        raise ValueError("app_name must be a non-empty string")
    if not user_id or not str(user_id).strip():
        raise ValueError("user_id must be a non-empty string")


def _parse_memshield_uri(uri: str) -> tuple[str, dict[str, Any]]:
    """Parse a memshield:// or postgresql:// URI into (postgres_dsn, config_overrides)."""
    parsed = urlparse(uri)
    query_params = parse_qs(parsed.query)
    overrides: dict[str, Any] = {}

    if "tenant_id" in query_params:
        overrides["tenant_id"] = query_params.pop("tenant_id")[0]
    if "agent_clearance" in query_params:
        overrides["agent_clearance"] = int(query_params.pop("agent_clearance")[0])
    if "default_scope" in query_params:
        overrides["default_scope"] = query_params.pop("default_scope")[0]
    if "default_min_clearance" in query_params:
        overrides["default_min_clearance"] = int(query_params.pop("default_min_clearance")[0])
    if "top_k" in query_params:
        overrides["top_k"] = int(query_params.pop("top_k")[0])
    if "table_name" in query_params:
        overrides["table_name"] = query_params.pop("table_name")[0]
    if "simulate_missing_app_filter" in query_params:
        val = query_params.pop("simulate_missing_app_filter")[0].lower()
        overrides["simulate_missing_app_filter"] = val in ("1", "true", "yes")

    remaining_query = urlencode(query_params, doseq=True)
    dsn = urlunparse(
        (
            "postgresql",
            parsed.netloc,
            parsed.path,
            parsed.params,
            remaining_query,
            parsed.fragment,
        )
    )
    return dsn, overrides


@dataclass
class QueryTelemetry(Mapping[str, Any]):
    """Telemetry snapshot recorded on `MemShieldMemoryService.last_query_telemetry`.

    Supports both attribute access (`telemetry.latency_ms`) and dictionary access
    (`telemetry["latency_ms"]`).
    """

    operation: str
    sql: str
    session_context: dict[str, str]
    latency_ms: float
    row_count: int
    simulate_missing_app_filter: bool
    table_name: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __getitem__(self, key: str) -> Any:
        return asdict(self)[key]

    def __iter__(self) -> Iterator[str]:
        return iter(asdict(self))

    def __len__(self) -> int:
        return len(asdict(self))


class MemShieldMemoryService(BaseMemoryService):
    """Zero-trust multi-tenant semantic memory service for Google ADK.

    Enforces tenant, user, and multi-agent clearance boundaries at the PostgreSQL
    kernel level using Row-Level Security (RLS) and transaction-local `set_config`.

    Blocking work (ONNX embedding and psycopg I/O) runs in a worker thread via
    `asyncio.to_thread`, so the ADK event loop is never stalled by memory calls.
    """

    def __init__(
        self,
        config: MemShieldConfig | None = None,
        *,
        dsn: str | None = None,
        uri: str | None = None,
        tenant_id: str | None = None,
        agent_clearance: int | None = None,
        default_scope: Literal["private", "tenant_shared"] | None = None,
        default_min_clearance: int | None = None,
        top_k: int | None = None,
        min_similarity: float | None = None,
        embedding_model: str | None = None,
        embedding_dim: int | None = None,
        table_name: str | None = None,
        simulate_missing_app_filter: bool | None = None,
        embed_fn: EmbedFn | None = None,
        pool: ConnectionPool | None = None,
    ) -> None:
        cfg_data: dict[str, Any] = config.model_dump() if config is not None else {}

        if uri is not None:
            parsed_dsn, uri_overrides = _parse_memshield_uri(uri)
            cfg_data["dsn"] = parsed_dsn
            cfg_data.update(uri_overrides)

        explicit_overrides = {
            "dsn": dsn,
            "tenant_id": tenant_id,
            "agent_clearance": agent_clearance,
            "default_scope": default_scope,
            "default_min_clearance": default_min_clearance,
            "top_k": top_k,
            "min_similarity": min_similarity,
            "embedding_model": embedding_model,
            "embedding_dim": embedding_dim,
            "table_name": table_name,
            "simulate_missing_app_filter": simulate_missing_app_filter,
        }
        for key, value in explicit_overrides.items():
            if value is not None:
                cfg_data[key] = value

        self.config = MemShieldConfig(**cfg_data)
        self.embedder = MemShieldEmbedder(
            model_name=self.config.embedding_model,
            expected_dim=self.config.embedding_dim,
            embed_fn=embed_fn,
        )
        self._pool = pool if pool is not None else _get_shared_pool(self.config.dsn)
        self.last_query_telemetry: QueryTelemetry | None = None

    def _rls_context(self, *, app_name: str, user_id: str) -> dict[str, str]:
        return {
            "app.current_app_name": str(app_name),
            "app.current_tenant_id": str(self.config.tenant_id),
            "app.current_user_id": str(user_id),
            "app.agent_clearance": str(self.config.agent_clearance),
        }

    @contextmanager
    def rls_transaction(
        self,
        *,
        app_name: str,
        user_id: str,
    ) -> Iterator[psycopg.Cursor[Any]]:
        """Yield a cursor inside an explicit transaction bound to the caller's RLS identity.

        Identity is bound with `set_config(..., is_local => true)`, so it is discarded when
        the transaction commits or rolls back and never bleeds into the next pooled
        checkout. Any custom SQL executed on the yielded cursor is subject to the RLS
        policies on `memories`, even if that SQL omits its own ownership filters.
        """
        _require_identity(app_name, user_id)
        context = self._rls_context(app_name=app_name, user_id=user_id)
        with self._pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            set_config('app.current_app_name', %s, true),
                            set_config('app.current_tenant_id', %s, true),
                            set_config('app.current_user_id', %s, true),
                            set_config('app.agent_clearance', %s, true);
                        """,
                        (
                            context["app.current_app_name"],
                            context["app.current_tenant_id"],
                            context["app.current_user_id"],
                            context["app.agent_clearance"],
                        ),
                    )
                    yield cur

    async def add_session_to_memory(self, session: Session) -> None:
        """Extract non-empty text parts from `session.events`, embed, and insert with RLS.

        Idempotent per event: ADK may add the same session several times during its
        lifetime, and previously stored `(session_id, event_id)` pairs are skipped.
        """
        session_meta: dict[str, Any] = {}
        if session.state:
            if "scope" in session.state:
                session_meta["scope"] = session.state["scope"]
            if "min_clearance" in session.state:
                session_meta["min_clearance"] = session.state["min_clearance"]

        await self.add_events_to_memory(
            app_name=session.app_name,
            user_id=session.user_id,
            events=session.events,
            session_id=session.id,
            custom_metadata=session_meta or None,
        )

    async def add_events_to_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        events: Sequence[Event],
        session_id: str | None = None,
        custom_metadata: Mapping[str, object] | None = None,
    ) -> None:
        """Append incremental ADK events into RLS-protected semantic memory."""
        base_meta = dict(custom_metadata) if custom_metadata else {}
        entries: list[MemoryEntry] = []

        for event in events:
            text = _extract_text_from_content(event.content)
            if not text:
                continue
            author = event.author or (
                event.content.role if event.content and event.content.role else "user"
            )
            ev_meta = dict(base_meta)
            if session_id is not None:
                ev_meta.setdefault("session_id", session_id)
            if event.id:
                ev_meta.setdefault("event_id", event.id)

            entries.append(
                MemoryEntry(
                    content=types.Content(
                        parts=[types.Part(text=text)],
                        role=author,
                    ),
                    author=author,
                    custom_metadata=ev_meta,
                )
            )

        if not entries:
            return

        await self.add_memory(
            app_name=app_name,
            user_id=user_id,
            memories=entries,
            custom_metadata=base_meta,
        )

    async def add_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        memories: Sequence[MemoryEntry],
        custom_metadata: Mapping[str, object] | None = None,
    ) -> None:
        """Directly ingest `MemoryEntry` items into RLS-protected PostgreSQL storage."""
        _require_identity(app_name, user_id)
        await asyncio.to_thread(
            self._add_memory_sync,
            app_name=app_name,
            user_id=user_id,
            memories=memories,
            custom_metadata=custom_metadata,
        )

    def _add_memory_sync(
        self,
        *,
        app_name: str,
        user_id: str,
        memories: Sequence[MemoryEntry],
        custom_metadata: Mapping[str, object] | None,
    ) -> None:
        base_meta = dict(custom_metadata) if custom_metadata else {}
        prepared: list[tuple[MemoryEntry, str, str, str, int, str | None, dict[str, Any]]] = []

        for entry in memories:
            text = _extract_text_from_content(entry.content)
            if not text:
                continue
            merged_meta = {**base_meta, **(entry.custom_metadata or {})}
            scope = str(merged_meta.pop("scope", self.config.default_scope))
            min_clearance = int(
                merged_meta.pop("min_clearance", self.config.default_min_clearance)
            )
            session_id = merged_meta.pop("session_id", None)
            author = entry.author or (
                entry.content.role if entry.content and entry.content.role else "user"
            )
            prepared.append(
                (entry, text, author, scope, min_clearance, session_id, merged_meta)
            )

        if not prepared:
            return

        texts = [item[1] for item in prepared]
        embeddings = self.embedder.embed_documents(texts)

        # Ownership columns always come from the authenticated call arguments and the
        # service config, never from caller-supplied metadata.
        table = self.config.table_name
        insert_sql = f"""
            INSERT INTO {table} (
                app_name, tenant_id, user_id, session_id, author,
                scope, min_clearance, content, custom_metadata, embedding
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector)
            ON CONFLICT (app_name, tenant_id, user_id, session_id, (custom_metadata->>'event_id'))
                WHERE custom_metadata ? 'event_id'
                DO NOTHING
            RETURNING id
        """

        t0 = time.perf_counter()
        inserted_count = 0
        with self.rls_transaction(app_name=app_name, user_id=user_id) as cur:
            for (
                entry,
                text,
                author,
                scope,
                min_clearance,
                session_id,
                meta,
            ), vec in zip(prepared, embeddings, strict=True):
                cur.execute(
                    insert_sql,
                    (
                        app_name,
                        self.config.tenant_id,
                        user_id,
                        session_id,
                        author,
                        scope,
                        min_clearance,
                        text,
                        json.dumps(meta),
                        _format_vector(vec),
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    continue  # duplicate (session_id, event_id) already stored
                if entry.id is None:
                    entry.id = str(row[0])
                inserted_count += 1

        latency_ms = (time.perf_counter() - t0) * 1000.0
        self.last_query_telemetry = QueryTelemetry(
            operation="add_memory",
            sql=insert_sql.strip(),
            session_context=self._rls_context(app_name=app_name, user_id=user_id),
            latency_ms=latency_ms,
            row_count=inserted_count,
            simulate_missing_app_filter=self.config.simulate_missing_app_filter,
            table_name=table,
        )

    async def search_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        query: str,
    ) -> SearchMemoryResponse:
        """Search semantic memories with transaction-local PostgreSQL RLS enforcement."""
        _require_identity(app_name, user_id)
        return await asyncio.to_thread(
            self._search_memory_sync, app_name=app_name, user_id=user_id, query=query
        )

    def _search_memory_sync(
        self,
        *,
        app_name: str,
        user_id: str,
        query: str,
    ) -> SearchMemoryResponse:
        query_vec = self.embedder.embed_query(query)
        vec_literal = _format_vector(query_vec)
        table = self.config.table_name

        if self.config.simulate_missing_app_filter:
            sql = f"""
                SELECT
                    id, app_name, tenant_id, user_id, session_id, author,
                    scope, min_clearance, content, custom_metadata, created_at,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM {table}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """
            params: tuple[Any, ...] = (vec_literal, vec_literal, self.config.top_k)
        else:
            # Defense in depth: the application-layer filter mirrors the RLS SELECT
            # policy, so neither layer alone is a single point of failure.
            sql = f"""
                SELECT
                    id, app_name, tenant_id, user_id, session_id, author,
                    scope, min_clearance, content, custom_metadata, created_at,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM {table}
                WHERE app_name = %s AND tenant_id = %s
                  AND (user_id = %s OR (scope = 'tenant_shared' AND min_clearance <= %s))
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """
            params = (
                vec_literal,
                app_name,
                self.config.tenant_id,
                user_id,
                self.config.agent_clearance,
                vec_literal,
                self.config.top_k,
            )

        t0 = time.perf_counter()
        with self.rls_transaction(app_name=app_name, user_id=user_id) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        latency_ms = (time.perf_counter() - t0) * 1000.0

        results: list[MemoryEntry] = []
        for row in rows:
            (
                row_id,
                row_app_name,
                row_tenant_id,
                row_user_id,
                row_session_id,
                row_author,
                row_scope,
                row_min_clearance,
                row_content,
                row_custom_meta,
                row_created_at,
                row_similarity,
            ) = row

            similarity_val = float(row_similarity)
            if (
                self.config.min_similarity is not None
                and similarity_val < self.config.min_similarity
            ):
                continue

            meta_dict: dict[str, Any] = (
                dict(row_custom_meta) if isinstance(row_custom_meta, Mapping) else {}
            )
            meta_dict.update(
                {
                    "app_name": row_app_name,
                    "tenant_id": row_tenant_id,
                    "user_id": row_user_id,
                    "session_id": row_session_id,
                    "scope": row_scope,
                    "min_clearance": int(row_min_clearance),
                    "similarity": similarity_val,
                }
            )
            role = row_author or "user"
            results.append(
                MemoryEntry(
                    id=str(row_id),
                    content=types.Content(
                        parts=[types.Part(text=str(row_content))],
                        role=role,
                    ),
                    author=role,
                    timestamp=row_created_at.isoformat() if row_created_at else None,
                    custom_metadata=meta_dict,
                )
            )

        self.last_query_telemetry = QueryTelemetry(
            operation="search_memory",
            sql=sql.strip(),
            session_context=self._rls_context(app_name=app_name, user_id=user_id),
            latency_ms=latency_ms,
            row_count=len(results),
            simulate_missing_app_filter=self.config.simulate_missing_app_filter,
            table_name=table,
        )
        return SearchMemoryResponse(memories=results)

    async def delete_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        memory_id: str | None = None,
    ) -> None:
        """Delete a specific memory ID (or all caller-owned memories) under RLS."""
        _require_identity(app_name, user_id)
        await asyncio.to_thread(
            self._delete_memory_sync, app_name=app_name, user_id=user_id, memory_id=memory_id
        )

    def _delete_memory_sync(
        self,
        *,
        app_name: str,
        user_id: str,
        memory_id: str | None,
    ) -> None:
        table = self.config.table_name
        owner_filter = "app_name = %s AND tenant_id = %s AND user_id = %s"
        owner_params: tuple[Any, ...] = (app_name, self.config.tenant_id, user_id)
        if memory_id is not None:
            sql = f"DELETE FROM {table} WHERE id = %s::uuid AND {owner_filter}"
            params: tuple[Any, ...] = (memory_id, *owner_params)
        else:
            sql = f"DELETE FROM {table} WHERE {owner_filter}"
            params = owner_params

        t0 = time.perf_counter()
        with self.rls_transaction(app_name=app_name, user_id=user_id) as cur:
            cur.execute(sql, params)
            deleted_count = cur.rowcount if cur.rowcount is not None else 0
        latency_ms = (time.perf_counter() - t0) * 1000.0

        self.last_query_telemetry = QueryTelemetry(
            operation="delete_memory",
            sql=sql,
            session_context=self._rls_context(app_name=app_name, user_id=user_id),
            latency_ms=latency_ms,
            row_count=deleted_count,
            simulate_missing_app_filter=self.config.simulate_missing_app_filter,
            table_name=table,
        )


def register_adk_uri(scheme: str = "memshield") -> None:
    """Register the `memshield://` URI scheme with Google ADK's ServiceRegistry."""
    from google.adk.cli.service_registry import get_service_registry

    def _factory(uri: str, **kwargs: Any) -> BaseMemoryService:
        kwargs_copy = dict(kwargs)
        kwargs_copy.pop("agents_dir", None)
        return MemShieldMemoryService(uri=uri, **kwargs_copy)

    get_service_registry().register_memory_service(scheme, _factory)
