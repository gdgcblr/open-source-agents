"""Baseline unprotected pgvector BaseMemoryService demonstrating common app-layer RAG flaws."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from adk_memshield import EmbedFn, MemShieldEmbedder, QueryTelemetry
from adk_memshield.service import _extract_text_from_content, _format_vector, _get_shared_pool
from google.adk.events.event import Event
from google.adk.memory.base_memory_service import BaseMemoryService, SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.sessions.session import Session
from google.genai import types
from psycopg_pool import ConnectionPool

FailureMode = Literal[
    "shared_tenant_no_user_filter",
    "adversarial_planted_lure",
    "param_spoof_user_id",
    "swarm_missing_clearance_filter",
    "strip_all_where_filters",
    "same_tier_shared_poisoning",
    "control",
]

_SPOOF_USER_RE = re.compile(r"(?:target_user_id|user_id)\s*=\s*([a-zA-Z0-9_]+)", re.IGNORECASE)


def extract_spoofed_user_id(query: str) -> str | None:
    """Return the `user_id=` / `target_user_id=` value a prompt injects into the tool call, if any."""
    match = _SPOOF_USER_RE.search(query)
    return match.group(1) if match else None


class UnprotectedPgVectorMemoryService(BaseMemoryService):
    """Standard shared-table pgvector memory service without PostgreSQL Row-Level Security.

    Relies entirely on application-layer SQL `WHERE` clauses against `memories_unprotected`.
    Supports configurable `failure_mode` presets matching real-world multi-tenant and
    multi-agent RAG implementation bugs (`MemLeak` and `AgentLeak`).
    """

    def __init__(
        self,
        *,
        dsn: str,
        tenant_id: str = "acme_corp",
        agent_clearance: int = 1,
        top_k: int = 3,
        table_name: str = "memories_unprotected",
        failure_mode: FailureMode = "shared_tenant_no_user_filter",
        simulate_missing_app_filter: bool = False,
        spoofed_user_id: str | None = None,
        embedding_model: str = "BAAI/bge-small-en-v1.5",
        embedding_dim: int = 384,
        embed_fn: EmbedFn | None = None,
        pool: ConnectionPool | None = None,
    ) -> None:
        self.dsn = dsn
        self.tenant_id = tenant_id
        self.agent_clearance = agent_clearance
        self.top_k = top_k
        self.table_name = table_name
        self.failure_mode: FailureMode = failure_mode
        self.simulate_missing_app_filter = simulate_missing_app_filter
        self.spoofed_user_id = spoofed_user_id
        self.embedder = MemShieldEmbedder(
            model_name=embedding_model,
            expected_dim=embedding_dim,
            embed_fn=embed_fn,
        )
        self._pool = pool if pool is not None else _get_shared_pool(dsn)
        self.last_query_telemetry: QueryTelemetry | None = None

    async def add_session_to_memory(self, session: Session) -> None:
        """Ingest session events into `memories_unprotected`.

        Mirrors adk-memshield's ingestion semantics (idempotent per `(session_id, event_id)`)
        so the two arena targets differ only in their read-side security model.
        """
        events: Sequence[Event] = session.events or []
        entries: list[MemoryEntry] = []
        for ev in events:
            text = _extract_text_from_content(ev.content)
            if not text:
                continue
            author = ev.author or "user"
            meta: dict[str, Any] = {"session_id": session.id}
            if ev.id:
                meta["event_id"] = ev.id
            entries.append(
                MemoryEntry(
                    content=types.Content(parts=[types.Part(text=text)], role=author),
                    author=author,
                    custom_metadata=meta,
                )
            )
        if entries:
            await self.add_memory(
                app_name=session.app_name,
                user_id=session.user_id,
                memories=entries,
            )

    async def add_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        memories: Sequence[MemoryEntry],
        custom_metadata: Mapping[str, object] | None = None,
    ) -> None:
        """Insert memory entries into `memories_unprotected` without RLS transaction binding."""
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
            scope = str(merged_meta.pop("scope", "private"))
            min_clearance = int(merged_meta.pop("min_clearance", 1))
            session_id = merged_meta.pop("session_id", None)
            author = entry.author or "user"
            prepared.append((entry, text, author, scope, min_clearance, session_id, merged_meta))

        if not prepared:
            return

        texts = [item[1] for item in prepared]
        embeddings = self.embedder.embed_documents(texts)

        insert_sql = f"""
            INSERT INTO {self.table_name} (
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
        inserted = 0
        with self._pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
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
                                self.tenant_id,
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
                        inserted += 1

        latency_ms = (time.perf_counter() - t0) * 1000.0
        self.last_query_telemetry = QueryTelemetry(
            operation="add_memory",
            sql=insert_sql.strip(),
            session_context={"rls_context": "NONE (Unprotected Table)"},
            latency_ms=latency_ms,
            row_count=inserted,
            simulate_missing_app_filter=self.simulate_missing_app_filter,
            table_name=self.table_name,
        )

    async def search_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        query: str,
    ) -> SearchMemoryResponse:
        """Search `memories_unprotected` using the active application-layer `failure_mode`."""
        return await asyncio.to_thread(
            self._search_memory_sync,
            app_name=app_name,
            user_id=user_id,
            query=query,
        )

    def _build_query_and_params(
        self,
        *,
        app_name: str,
        user_id: str,
        query: str,
        vec_literal: str,
    ) -> tuple[str, tuple[Any, ...], dict[str, str]]:
        effective_mode = (
            "strip_all_where_filters"
            if self.simulate_missing_app_filter
            else self.failure_mode
        )
        select_cols = f"""
            SELECT
                id, app_name, tenant_id, user_id, session_id, author,
                scope, min_clearance, content, custom_metadata, created_at,
                1 - (embedding <=> %s::vector) AS similarity
            FROM {self.table_name}
        """

        if effective_mode == "strip_all_where_filters":
            sql = f"""{select_cols}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """
            params: tuple[Any, ...] = (vec_literal, vec_literal, self.top_k)
            ctx = {
                "rls_policy": "DISABLED (Table has no Row-Level Security)",
                "failure_mode": "strip_all_where_filters (No SQL WHERE clause)",
                "caller_identity": f"{user_id} (tenant={self.tenant_id}, clr={self.agent_clearance})",
            }
            return sql, params, ctx

        if effective_mode == "shared_tenant_no_user_filter":
            # S1: Filters by tenant_id only, omitting per-user ownership check
            sql = f"""{select_cols}
            WHERE app_name = %s AND tenant_id = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """
            params = (vec_literal, app_name, self.tenant_id, vec_literal, self.top_k)
            ctx = {
                "rls_policy": "DISABLED (Table has no Row-Level Security)",
                "failure_mode": "shared_tenant_no_user_filter (Missing WHERE user_id = %s)",
                "app_filter_bound": f"tenant_id='{self.tenant_id}' (user_id omitted!)",
            }
            return sql, params, ctx

        if effective_mode == "adversarial_planted_lure":
            # S2: Filters by tenant_id and clearance level, but allows all Clearance-1 users
            # in the shared tenant vector index to collide (Mallory's planted lure hijacks Rank #1)
            sql = f"""{select_cols}
            WHERE app_name = %s AND tenant_id = %s
              AND min_clearance <= %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """
            params = (
                vec_literal,
                app_name,
                self.tenant_id,
                self.agent_clearance,
                vec_literal,
                self.top_k,
            )
            ctx = {
                "rls_policy": "DISABLED (Table has no Row-Level Security)",
                "failure_mode": "adversarial_planted_lure (Shared tenant top-K index collision)",
                "app_filter_bound": f"tenant_id='{self.tenant_id}', min_clearance<={self.agent_clearance}",
            }
            return sql, params, ctx

        if effective_mode == "param_spoof_user_id":
            # S3: Confused-deputy tool call where target_user_id from prompt/tool args overrides caller user_id
            target_user = self.spoofed_user_id or extract_spoofed_user_id(query) or "bob_cfo"
            sql = f"""{select_cols}
            WHERE app_name = %s AND tenant_id = %s
              AND user_id = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """
            params = (vec_literal, app_name, self.tenant_id, target_user, vec_literal, self.top_k)
            ctx = {
                "rls_policy": "DISABLED (Table has no Row-Level Security)",
                "failure_mode": f"param_spoof_user_id (Tool arg overrode user_id='{target_user}')",
                "authenticated_session_user": user_id,
                "spoofed_sql_param_user": target_user,
            }
            return sql, params, ctx

        if effective_mode == "swarm_missing_clearance_filter":
            # S4: Filters private rows by user_id and shared rows by scope='tenant_shared',
            # but forgets `AND min_clearance <= agent_clearance` (AgentLeak vertical read-up)
            sql = f"""{select_cols}
            WHERE app_name = %s AND tenant_id = %s
              AND (user_id = %s OR scope = 'tenant_shared')
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """
            params = (vec_literal, app_name, self.tenant_id, user_id, vec_literal, self.top_k)
            ctx = {
                "rls_policy": "DISABLED (Table has no Row-Level Security)",
                "failure_mode": "swarm_missing_clearance_filter (Missing min_clearance <= agent_clearance)",
                "app_filter_bound": f"user_id='{user_id}' OR scope='tenant_shared' (clearance unchecked!)",
            }
            return sql, params, ctx

        # Control mode (and S6): complete, correct application-layer filter. In S6 the
        # same-tier shared lure is *authorized* here and under RLS alike.
        sql = f"""{select_cols}
        WHERE app_name = %s AND tenant_id = %s
          AND (user_id = %s OR (scope = 'tenant_shared' AND min_clearance <= %s))
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """
        params = (
            vec_literal,
            app_name,
            self.tenant_id,
            user_id,
            self.agent_clearance,
            vec_literal,
            self.top_k,
        )
        ctx = {
            "rls_policy": "DISABLED (App-layer filter only)",
            "failure_mode": (
                "same_tier_shared_poisoning (correct app filter; same-tier shared rows are authorized)"
                if effective_mode == "same_tier_shared_poisoning"
                else "control"
            ),
            "app_filter_bound": f"tenant_id='{self.tenant_id}', user_id='{user_id}', clr<={self.agent_clearance}",
        }
        return sql, params, ctx

    def _search_memory_sync(
        self,
        *,
        app_name: str,
        user_id: str,
        query: str,
    ) -> SearchMemoryResponse:
        query_vec = self.embedder.embed_query(query)
        vec_literal = _format_vector(query_vec)

        sql, params, ctx = self._build_query_and_params(
            app_name=app_name,
            user_id=user_id,
            query=query,
            vec_literal=vec_literal,
        )

        t0 = time.perf_counter()
        with self._pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
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
                    "similarity": float(row_similarity),
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
            sql="\n".join(line.strip() for line in sql.strip().splitlines()),
            session_context=ctx,
            latency_ms=latency_ms,
            row_count=len(results),
            simulate_missing_app_filter=self.simulate_missing_app_filter,
            table_name=self.table_name,
        )
        return SearchMemoryResponse(memories=results)
