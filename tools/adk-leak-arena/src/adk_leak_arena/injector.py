"""Red-Team CTF Memory Injector: side-by-side poisoned writes against both arena targets.

The acting persona is the *authenticated* writer. `claimed_owner_id` is the owner column the
write tries to set, so a mismatch models insert-owner spoofing (a confused-deputy tool call
or compromised application code writing on someone else's behalf).

- Unprotected: the app trusts the row values and inserts them as given.
- adk-memshield: the transaction identity is bound to the acting persona with the package's
  own `rls_transaction`. When the claimed owner is the actor, the public `add_memory` API is
  used; otherwise the spoofed INSERT is issued inside that RLS transaction. Either way the
  PostgreSQL `WITH CHECK` policy decides; nothing is pre-filtered in Python.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

import psycopg
from adk_memshield import MemShieldMemoryService
from google.adk.memory.memory_entry import MemoryEntry
from google.genai import types

from .config import ArenaConfig
from .dataset import INJECTOR_PERSONAS, CanaryCarrier, register_injected_canary
from .embedding import get_cached_embed_fn
from .unprotected_service import UnprotectedPgVectorMemoryService

_SPOOF_INSERT_SQL = """
INSERT INTO memories (
    app_name, tenant_id, user_id, session_id, author,
    scope, min_clearance, content, custom_metadata, embedding
)
VALUES (%s, %s, %s, NULL, 'user', %s, %s, %s, %s::jsonb, %s::vector)
RETURNING id
""".strip()

_SET_CONFIG_SQL = (
    "SELECT set_config('app.current_app_name', {app}, true),\n"
    "       set_config('app.current_tenant_id', {tenant}, true),\n"
    "       set_config('app.current_user_id', {user}, true),\n"
    "       set_config('app.agent_clearance', {clr}, true);"
)


def _lit(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in vec) + "]"


def _error_payload(exc: Exception) -> dict[str, Any]:
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return {
        "error_class": type(exc).__name__,
        "sqlstate": getattr(exc, "sqlstate", None),
        "error": message[:300],
    }


def probe_query_for(content: str) -> str:
    """Return the question a query-mirroring lure targets (text up to its first '?')."""
    head, sep, _ = content.partition("?")
    return (head + sep).strip() if sep and len(head) <= 240 else content[:240]


async def inject_memory(
    config: ArenaConfig,
    *,
    acting_persona: str,
    claimed_owner_id: str | None,
    scope: str,
    min_clearance: int,
    content: str,
    canary_token: str | None,
) -> dict[str, Any]:
    actor = INJECTOR_PERSONAS[acting_persona]
    owner = (claimed_owner_id or "").strip() or actor.user_id
    final_content = content.strip()
    if canary_token and canary_token not in final_content:
        final_content = f"{final_content} [{canary_token}]"

    owner_spoof = owner != actor.user_id
    write_up = scope == "tenant_shared" and min_clearance > actor.clearance
    seed_key = f"ctf_{uuid.uuid4().hex[:8]}"
    meta = {
        "seed_key": seed_key,
        "injected": True,
        "adversarial": True,
        "acting_persona": actor.user_id,
        "persona_label": f"CTF injection by {actor.user_id}",
    }
    if canary_token:
        meta["canary"] = canary_token

    embed_fn = get_cached_embed_fn(config.embedding_model, config.embedding_dim)

    def _entry() -> MemoryEntry:
        return MemoryEntry(
            content=types.Content(parts=[types.Part(text=final_content)], role="user"),
            author="user",
            custom_metadata={**meta, "scope": scope, "min_clearance": min_clearance},
        )

    # ---- Left: unprotected app-layer write (row values trusted as submitted) ----
    unp = UnprotectedPgVectorMemoryService(
        dsn=config.db_dsn,
        tenant_id=actor.tenant_id,
        agent_clearance=actor.clearance,
        embed_fn=embed_fn,
    )
    left: dict[str, Any] = {"target": "unprotected", "path": "UnprotectedPgVectorMemoryService.add_memory"}
    t0 = time.perf_counter()
    try:
        entry = _entry()
        await unp.add_memory(app_name=config.app_name, user_id=owner, memories=[entry])
        left.update(accepted=True, row_id=entry.id, error=None, error_class=None, sqlstate=None)
    except Exception as exc:  # pragma: no cover - the unprotected table has no write policy
        left.update(accepted=False, row_id=None, **_error_payload(exc))
    left["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
    left["sql"] = unp.last_query_telemetry.sql if unp.last_query_telemetry else ""
    left["identity_context"] = "-- No RLS identity bound; owner/scope/clearance trusted from the request."

    # ---- Right: adk-memshield write under the actor's transaction-local RLS identity ----
    ms = MemShieldMemoryService(
        dsn=config.db_dsn,
        tenant_id=actor.tenant_id,
        agent_clearance=actor.clearance,
        embed_fn=embed_fn,
    )
    right: dict[str, Any] = {"target": "memshield"}
    t0 = time.perf_counter()
    try:
        if not owner_spoof:
            right["path"] = "MemShieldMemoryService.add_memory (owner bound from session)"
            entry = _entry()
            await ms.add_memory(app_name=config.app_name, user_id=actor.user_id, memories=[entry])
            right["sql"] = ms.last_query_telemetry.sql if ms.last_query_telemetry else ""
            row_id = entry.id
        else:
            right["path"] = "MemShieldMemoryService.rls_transaction(actor) + INSERT with claimed owner"
            right["sql"] = _SPOOF_INSERT_SQL
            vec = _vector_literal(embed_fn([final_content])[0])

            def _spoofed_insert() -> str | None:
                with ms.rls_transaction(app_name=config.app_name, user_id=actor.user_id) as cur:
                    cur.execute(
                        _SPOOF_INSERT_SQL,
                        (
                            config.app_name,
                            actor.tenant_id,
                            owner,
                            scope,
                            min_clearance,
                            final_content,
                            json.dumps(meta),
                            vec,
                        ),
                    )
                    row = cur.fetchone()
                    return str(row[0]) if row else None

            row_id = await asyncio.to_thread(_spoofed_insert)
        right.update(accepted=True, row_id=row_id, error=None, error_class=None, sqlstate=None)
    except psycopg.Error as exc:
        right.update(accepted=False, row_id=None, **_error_payload(exc))
    right["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
    right["identity_context"] = _SET_CONFIG_SQL.format(
        app=_lit(config.app_name),
        tenant=_lit(actor.tenant_id),
        user=_lit(actor.user_id),
        clr=_lit(actor.clearance),
    )

    if canary_token and (left["accepted"] or right["accepted"]):
        register_injected_canary(
            CanaryCarrier(
                token=canary_token,
                tenant_id=actor.tenant_id,
                user_id=owner,
                scope=scope,
                min_clearance=min_clearance,
                adversarial=True,
            )
        )

    if owner_spoof and write_up:
        attack = "owner spoofing + clearance write-up"
    elif owner_spoof:
        attack = "insert owner spoofing"
    elif write_up:
        attack = "clearance write-up escalation"
    elif scope == "tenant_shared":
        attack = "same-tier shared lure (S6 boundary)"
    else:
        attack = "private lure in the actor's own namespace"

    if right["accepted"] and scope == "tenant_shared":
        verdict = (
            "Both targets accepted: the write is within the actor's own tenant and clearance, so RLS "
            "permits it. Every caller at this tier can now retrieve it (Scenario 6 boundary)."
        )
    elif right["accepted"]:
        verdict = (
            "Both targets accepted a private row owned by the actor. Probe as alice_analyst: the "
            "unprotected S1/S2 filters can surface it; RLS keeps it out of her results."
        )
    elif left["accepted"]:
        verdict = (
            "Unprotected ACCEPTED the poisoned write; adk-memshield was REJECTED by the PostgreSQL "
            f"WITH CHECK policy ({right.get('error_class')}, SQLSTATE {right.get('sqlstate')})."
        )
    else:
        verdict = "Both targets rejected the write."

    return {
        "request": {
            "acting_persona": actor.user_id,
            "actor_tenant_id": actor.tenant_id,
            "actor_clearance": actor.clearance,
            "claimed_owner_id": owner,
            "scope": scope,
            "min_clearance": min_clearance,
            "content": final_content,
            "canary_token": canary_token,
            "seed_key": seed_key,
        },
        "analysis": {
            "attack": attack,
            "owner_spoof": owner_spoof,
            "write_up": write_up,
            "verdict": verdict,
        },
        "canary_registered": bool(canary_token and (left["accepted"] or right["accepted"])),
        "probe_query": probe_query_for(final_content),
        "unprotected": left,
        "memshield": right,
    }
