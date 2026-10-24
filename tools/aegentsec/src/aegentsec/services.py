import secrets
from datetime import UTC, datetime
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from aegentsec.database import Database

# Exact `resource:action` names only; wildcards can never be created.
SCOPE_PATTERN = r"^[a-z][a-z0-9_-]*:[a-z][a-z0-9_-]*$"
_hasher = PasswordHasher()
# Verified when a client_id is unknown so unknown and wrong-secret requests cost the same.
_DUMMY_HASH = _hasher.hash("aegentsec-dummy-secret")


class ServiceError(Exception):
    def __init__(self, code: str, status: int = 400):
        self.code = code
        self.status = status
        super().__init__(code)


def has_permission(granted_scopes: set[str], required_scope: str, catalogue: set[str]) -> bool:
    return required_scope in catalogue and required_scope in granted_scopes


class IAMService:
    def __init__(self, db: Database):
        self.db = db

    async def register_enterprise(self, name: str) -> dict:
        enterprise_id = f"ent_{uuid4().hex}"
        await self.db.create_enterprise(enterprise_id, name)
        await self.audit("enterprise_registered", enterprise_id=enterprise_id, name=name)
        return {"enterprise_id": enterprise_id, "name": name, "is_active": True}

    async def register_agent(self, enterprise_id: str, name: str, scopes: list[str]) -> dict:
        granted = await self.validate_scopes(scopes)
        enterprise = await self.db.get_enterprise(enterprise_id)
        if enterprise is None:
            raise ServiceError("enterprise_not_found", 404)
        if not enterprise["is_active"]:
            raise ServiceError("enterprise_inactive", 403)
        agent_id = f"agt_{uuid4().hex}"
        client_id = f"cli_{uuid4().hex}"
        secret = secrets.token_urlsafe(48)
        now = datetime.now(UTC).isoformat()
        await self.db.create_agent(
            agent_id, enterprise_id, name, client_id, _hasher.hash(secret), granted, now
        )
        await self.audit(
            "agent_registered",
            agent_id=agent_id,
            enterprise_id=enterprise_id,
            name=name,
            scopes=granted,
        )
        return {
            "agent_id": agent_id,
            "enterprise_id": enterprise_id,
            "client_id": client_id,
            "client_secret": secret,
            "scopes": granted,
        }

    async def authenticate(self, client_id: str, client_secret: str) -> dict:
        agent = await self.db.get_agent_by_client_id(client_id)
        try:
            _hasher.verify(agent["client_secret_hash"] if agent else _DUMMY_HASH, client_secret)
        except VerifyMismatchError as exc:
            raise ServiceError("invalid_client", 401) from exc
        if agent is None:
            raise ServiceError("invalid_client", 401)
        if not agent["is_active"]:
            raise ServiceError("invalid_client", 401)
        enterprise = await self.db.get_enterprise(agent["enterprise_id"])
        if enterprise is None or not enterprise["is_active"]:
            raise ServiceError("invalid_client", 401)
        return agent

    async def active_agent(self, agent_id: str) -> dict | None:
        agent = await self.db.get_agent(agent_id)
        if agent is None or not agent["is_active"]:
            return None
        enterprise = await self.db.get_enterprise(agent["enterprise_id"])
        return agent if enterprise and enterprise["is_active"] else None

    async def set_agent_active(self, agent_id: str, active: bool) -> dict:
        now = datetime.now(UTC).isoformat()
        if not await self.db.set_agent_active(agent_id, active, now):
            raise ServiceError("agent_not_found", 404)
        agent = await self.db.get_agent(agent_id)
        await self.audit(
            "agent_activated" if active else "agent_deactivated",
            agent_id=agent_id,
            enterprise_id=agent["enterprise_id"],
        )
        return {"agent_id": agent_id, "is_active": active}

    async def set_enterprise_active(self, enterprise_id: str, active: bool) -> dict:
        if not await self.db.set_enterprise_active(enterprise_id, active):
            raise ServiceError("enterprise_not_found", 404)
        await self.audit(
            "enterprise_activated" if active else "enterprise_deactivated",
            enterprise_id=enterprise_id,
        )
        return {"enterprise_id": enterprise_id, "is_active": active}

    async def audit(
        self,
        event_type: str,
        agent_id: str | None = None,
        enterprise_id: str | None = None,
        **detail: object,
    ) -> None:
        """Record a security event. Never pass secrets or tokens as detail."""
        now = datetime.now(UTC).isoformat()
        await self.db.add_audit_event(event_type, agent_id, enterprise_id, detail, now)

    async def audit_events(self, limit: int = 50) -> list[dict]:
        return await self.db.list_audit_events(max(1, min(limit, 500)))

    async def scope_names(self) -> set[str]:
        return {row["scope"] for row in await self.db.list_scopes()}

    async def validate_scopes(self, scopes: list[str]) -> list[str]:
        catalogue = await self.scope_names()
        if any(scope not in catalogue for scope in scopes):
            raise ServiceError("invalid_scope")
        return sorted(set(scopes))

    async def create_scope(self, scope: str, description: str) -> dict:
        if not await self.db.create_scope(scope, description):
            raise ServiceError("scope_exists", 409)
        await self.audit("scope_created", scope=scope)
        return {"scope": scope, "description": description}

    async def delete_scope(self, scope: str) -> dict:
        if scope not in await self.scope_names():
            raise ServiceError("scope_not_found", 404)
        if await self.db.count_agents_with_scope(scope):
            raise ServiceError("scope_in_use", 409)
        await self.db.delete_scope(scope)
        await self.audit("scope_deleted", scope=scope)
        return {"scope": scope, "deleted": True}
