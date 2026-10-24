"""Quickstart: one shared `memories` table, two users, and PostgreSQL deciding who sees what.

Run against the bundled database:

    docker compose -p adk-memshield up -d db
    docker compose -p adk-memshield run --rm test python examples/quickstart.py

Environment (all optional):
    MEMSHIELD_DB_DSN           non-superuser app role DSN (read by MemShieldConfig)
    MEMSHIELD_ADMIN_DSN        admin DSN, used here only to reset this example's rows
    MEMSHIELD_TENANT_ID        tenant bound to the service (default: acme_corp)
    MEMSHIELD_AGENT_CLEARANCE  clearance of the searching agent, 1..5 (default: 1)
"""

from __future__ import annotations

import asyncio
import os

import psycopg
from google.adk.memory.memory_entry import MemoryEntry
from google.genai import types

from adk_memshield import MemShieldConfig, MemShieldMemoryService

APP_NAME = "memshield_quickstart"
ADMIN_DSN = os.environ.get(
    "MEMSHIELD_ADMIN_DSN",
    "postgresql://postgres:postgres_admin_pass@localhost:54329/memshield",
)
TENANT_ID = os.environ.get("MEMSHIELD_TENANT_ID", "acme_corp")
AGENT_CLEARANCE = int(os.environ.get("MEMSHIELD_AGENT_CLEARANCE", "1"))
ZERO_VECTOR = "[" + ",".join(["0"] * 384) + "]"


def _entry(text: str, **metadata: object) -> MemoryEntry:
    return MemoryEntry(
        content=types.Content(parts=[types.Part(text=text)]), custom_metadata=metadata
    )


async def main() -> None:
    # Reset only this example's rows so the script is re-runnable.
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        conn.execute("DELETE FROM memories WHERE app_name = %s", (APP_NAME,))

    agent = MemShieldMemoryService(
        MemShieldConfig(tenant_id=TENANT_ID, agent_clearance=AGENT_CLEARANCE)
    )
    executive = MemShieldMemoryService(MemShieldConfig(tenant_id=TENANT_ID, agent_clearance=3))

    await agent.add_memory(
        app_name=APP_NAME,
        user_id="alice",
        memories=[_entry("Alice's staging sandbox API key is SANDBOX-ALICE-101.")],
    )
    await agent.add_memory(
        app_name=APP_NAME,
        user_id="bob",
        memories=[
            _entry("Bob's production KMS failover recovery key is KMS-ROOT-8821-OMEGA."),
            _entry(
                "Support runbook: API key rotation requests go through the self-service portal.",
                scope="tenant_shared",
                min_clearance=1,
            ),
        ],
    )
    await executive.add_memory(
        app_name=APP_NAME,
        user_id="exec_agent",
        memories=[
            _entry(
                "Board memo: Project Titan API platform budget is TITAN-EXEC-300.",
                scope="tenant_shared",
                min_clearance=3,
            )
        ],
    )

    query = "What are the production API keys and KMS recovery keys?"
    print(f"tenant={TENANT_ID} clearance={AGENT_CLEARANCE} caller=alice")
    print(f"query: {query!r}\n")

    response = await agent.search_memory(app_name=APP_NAME, user_id="alice", query=query)
    print(f"search_memory -> {len(response.memories)} row(s) visible to alice:")
    for entry in response.memories:
        meta = entry.custom_metadata
        print(
            f"  [{meta['scope']:<13} clr>={meta['min_clearance']}] "
            f"sim={meta['similarity']:.3f}  {entry.content.parts[0].text}"
        )

    # Custom SQL with no WHERE clause still runs under alice's RLS identity.
    with agent.rls_transaction(app_name=APP_NAME, user_id="alice") as cur:
        cur.execute("SELECT count(*) FROM memories")
        visible = cur.fetchone()[0]
    with psycopg.connect(ADMIN_DSN) as conn:
        total = conn.execute(
            "SELECT count(*) FROM memories WHERE app_name = %s", (APP_NAME,)
        ).fetchone()[0]
    print(f"\nSELECT count(*) FROM memories  (no WHERE, as alice): {visible} of {total} rows")

    # Alice tries to plant a memory in Bob's namespace.
    try:
        with agent.rls_transaction(app_name=APP_NAME, user_id="alice") as cur:
            cur.execute(
                "INSERT INTO memories (app_name, tenant_id, user_id, content, embedding) "
                "VALUES (%s, %s, %s, %s, %s::vector)",
                (APP_NAME, TENANT_ID, "bob", "Spoofed note planted by alice.", ZERO_VECTOR),
            )
        print("owner-spoof INSERT as bob: ACCEPTED (unexpected)")
    except psycopg.errors.InsufficientPrivilege as exc:
        print(f"owner-spoof INSERT as bob: REJECTED (SQLSTATE {exc.sqlstate}) {exc.diag.message_primary}")


if __name__ == "__main__":
    asyncio.run(main())
