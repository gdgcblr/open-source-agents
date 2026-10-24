import json
from pathlib import Path

import aiosqlite

# Seeded on startup so a fresh database works for the demo; administrators can add more.
DEFAULT_SCOPES = {
    "inventory:read": "Read inventory records",
    "inventory:write": "Create and update inventory records",
    "inventory:delete": "Delete inventory records",
    "purchase:read": "Read purchase orders",
    "purchase:create": "Create purchase orders",
}


class Database:
    def __init__(self, path: Path):
        self.path = path

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA foreign_keys = ON")
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS enterprises (
                enterprise_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                enterprise_id TEXT NOT NULL REFERENCES enterprises(enterprise_id),
                name TEXT NOT NULL,
                client_id TEXT NOT NULL UNIQUE,
                client_secret_hash TEXT NOT NULL,
                scopes TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_agents_enterprise ON agents(enterprise_id);
            CREATE TABLE IF NOT EXISTS scopes (
                scope TEXT PRIMARY KEY,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                agent_id TEXT,
                enterprise_id TEXT,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        await self.conn.executemany(
            "INSERT OR IGNORE INTO scopes (scope, description) VALUES (?, ?)",
            list(DEFAULT_SCOPES.items()),
        )
        await self.conn.commit()

    async def close(self) -> None:
        await self.conn.close()

    async def create_enterprise(self, enterprise_id: str, name: str) -> None:
        await self.conn.execute(
            "INSERT INTO enterprises (enterprise_id, name) VALUES (?, ?)", (enterprise_id, name)
        )
        await self.conn.commit()

    async def get_enterprise(self, enterprise_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM enterprises WHERE enterprise_id = ?", (enterprise_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def create_agent(
        self,
        agent_id: str,
        enterprise_id: str,
        name: str,
        client_id: str,
        secret_hash: str,
        scopes: list[str],
        now: str,
    ) -> None:
        await self.conn.execute(
            """INSERT INTO agents
            (agent_id, enterprise_id, name, client_id, client_secret_hash, scopes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (agent_id, enterprise_id, name, client_id, secret_hash, json.dumps(scopes), now, now),
        )
        await self.conn.commit()

    def _agent(self, row: aiosqlite.Row | None) -> dict | None:
        if row is None:
            return None
        agent = dict(row)
        agent["scopes"] = json.loads(agent["scopes"])
        return agent

    async def get_agent(self, agent_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
        ) as cursor:
            return self._agent(await cursor.fetchone())

    async def get_agent_by_client_id(self, client_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM agents WHERE client_id = ?", (client_id,)
        ) as cursor:
            return self._agent(await cursor.fetchone())

    async def set_agent_active(self, agent_id: str, active: bool, now: str) -> bool:
        cursor = await self.conn.execute(
            "UPDATE agents SET is_active = ?, updated_at = ? WHERE agent_id = ?",
            (int(active), now, agent_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def set_enterprise_active(self, enterprise_id: str, active: bool) -> bool:
        cursor = await self.conn.execute(
            "UPDATE enterprises SET is_active = ? WHERE enterprise_id = ?",
            (int(active), enterprise_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def add_audit_event(
        self,
        event_type: str,
        agent_id: str | None,
        enterprise_id: str | None,
        detail: dict,
        now: str,
    ) -> None:
        await self.conn.execute(
            """INSERT INTO audit_events (event_type, agent_id, enterprise_id, detail, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            (event_type, agent_id, enterprise_id, json.dumps(detail), now),
        )
        await self.conn.commit()

    async def list_audit_events(self, limit: int) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM audit_events ORDER BY event_id DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
        events = [dict(row) for row in rows]
        for event in events:
            event["detail"] = json.loads(event["detail"])
        return events

    async def create_scope(self, scope: str, description: str) -> bool:
        cursor = await self.conn.execute(
            "INSERT OR IGNORE INTO scopes (scope, description) VALUES (?, ?)", (scope, description)
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def list_scopes(self) -> list[dict]:
        async with self.conn.execute("SELECT * FROM scopes ORDER BY scope") as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def count_agents_with_scope(self, scope: str) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) FROM agents, json_each(agents.scopes) WHERE json_each.value = ?",
            (scope,),
        ) as cursor:
            return (await cursor.fetchone())[0]

    async def delete_scope(self, scope: str) -> bool:
        cursor = await self.conn.execute("DELETE FROM scopes WHERE scope = ?", (scope,))
        await self.conn.commit()
        return cursor.rowcount > 0
