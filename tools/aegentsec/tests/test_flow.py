import asyncio
import json
import socket
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
import jwt
import pytest
import uvicorn
from aegentsec_sdk import AegentSecVerifier, AgentIdentity, TokenVerificationError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI

from aegentsec.application import create_app
from aegentsec.config import Settings

ADMIN_KEY = "test-admin-key-" + "x" * 32


@pytest.fixture
def settings(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "private.pem"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return Settings(
        _env_file=None,
        database_path=tmp_path / "test.sqlite3",
        iam_private_key_path=key_path,
        admin_api_key=ADMIN_KEY,
    )


@asynccontextmanager
async def client_for(settings):
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000"
        ) as client,
    ):
        yield app, client


async def register(client, scopes):
    headers = {"X-Admin-Api-Key": ADMIN_KEY}
    enterprise = await client.post("/api/v1/enterprises", json={"name": "Acme"}, headers=headers)
    assert enterprise.status_code == 201
    agent = await client.post(
        "/api/v1/agents",
        json={
            "enterprise_id": enterprise.json()["enterprise_id"],
            "name": "Inventory",
            "scopes": scopes,
        },
        headers=headers,
    )
    assert agent.status_code == 201
    return agent.json()


async def token(client, agent, audience, scope=""):
    return await client.post(
        "/api/v1/auth/token",
        auth=(agent["client_id"], agent["client_secret"]),
        data={"grant_type": "client_credentials", "resource": audience, "scope": scope},
    )


@pytest.mark.asyncio
async def test_registration_and_client_credentials(settings):
    async with client_for(settings) as (app, client):
        assert (
            await client.post("/api/v1/enterprises", json={"name": "No admin"})
        ).status_code == 401
        agent = await register(client, ["inventory:read"])
        stored = await app.state.iam.db.get_agent(agent["agent_id"])
        assert stored["client_secret_hash"] != agent["client_secret"]
        assert agent["client_secret"] not in str(stored)
        assert (await token(client, agent, "http://localhost:8001", "purchase:create")).json() == {
            "error": "invalid_scope"
        }
        assert (await token(client, agent, "http://evil.example")).json() == {
            "error": "invalid_target"
        }
        bad = dict(agent, client_secret="wrong")
        assert (await token(client, bad, "http://localhost:8001")).status_code == 401
        good = await token(client, agent, "http://localhost:8001")
        assert good.status_code == 200
        claims = app.state.tokens.verify(good.json()["access_token"], "http://localhost:8001")
        assert claims["sub"] == agent["agent_id"]
        with pytest.raises(jwt.InvalidAudienceError):
            app.state.tokens.verify(good.json()["access_token"], settings.mcp_resource_uri)
        assert "private" not in str((await client.get("/.well-known/jwks.json")).json())


@pytest.mark.asyncio
async def test_sdk_verification_and_scope(settings):
    async with client_for(settings) as (app, client):
        agent = await register(client, ["inventory:read"])
        response = await token(client, agent, settings.inventory_api_audience)
        access_token = response.json()["access_token"]
        verifier = AegentSecVerifier(
            settings.iam_issuer,
            settings.inventory_api_audience,
            f"{settings.iam_issuer}/.well-known/jwks.json",
        )
        jwk = app.state.tokens.jwks()["keys"][0]

        async def key(_kid):
            return jwk

        verifier._key = key
        identity = await verifier.verify(access_token)
        assert identity.agent_id == agent["agent_id"]
        assert identity.scopes == {"inventory:read"}
        assert (
            await verifier.require_scope("inventory:read")(
                httpx.Request(
                    "GET",
                    "http://localhost:8001",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            )
        ) == identity
        with pytest.raises(TokenVerificationError):
            await verifier.verify(access_token + "broken")


@pytest.mark.asyncio
async def test_mcp_http_requires_authentication(settings):
    async with client_for(settings) as (_app, client):
        response = await client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_mcp_tools_use_authenticated_identity(settings):
    async with client_for(settings) as (_app, client):
        agent = await register(client, ["inventory:read"])
        response = await token(client, agent, settings.mcp_resource_uri)
        bearer = response.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {bearer}",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        }

        async def call(name, arguments):
            return await client.post(
                "/mcp/",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                },
            )

        who = await call("whoami", {})
        assert who.status_code == 200, who.text
        assert (
            json.loads(who.json()["result"]["content"][0]["text"])["agent_id"] == agent["agent_id"]
        )
        denied = await call("check_permission", {"resource": "purchase", "action": "create"})
        assert json.loads(denied.json()["result"]["content"][0]["text"])["allowed"] is False
        permissions = await call("list_my_permissions", {})
        assert json.loads(permissions.json()["result"]["content"][0]["text"])["scopes"] == [
            "inventory:read"
        ]
        forged = await call("whoami", {"agent_id": "someone_else"})
        assert (
            json.loads(forged.json()["result"]["content"][0]["text"])["agent_id"]
            == agent["agent_id"]
        )
        api_token = (await token(client, agent, settings.inventory_api_audience)).json()[
            "access_token"
        ]
        wrong_audience = await client.post(
            "/mcp/",
            headers={**headers, "Authorization": f"Bearer {api_token}"},
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert wrong_audience.status_code == 401


@pytest.mark.asyncio
async def test_deactivated_agent_and_enterprise_cannot_get_tokens(settings):
    async with client_for(settings) as (app, client):
        agent = await register(client, ["inventory:read"])
        db = app.state.iam.db
        await db.conn.execute(
            "UPDATE agents SET is_active = 0 WHERE agent_id = ?", (agent["agent_id"],)
        )
        await db.conn.commit()
        assert (await token(client, agent, settings.inventory_api_audience)).status_code == 401
        await db.conn.execute(
            "UPDATE agents SET is_active = 1 WHERE agent_id = ?", (agent["agent_id"],)
        )
        await db.conn.execute(
            "UPDATE enterprises SET is_active = 0 WHERE enterprise_id = ?",
            (agent["enterprise_id"],),
        )
        await db.conn.commit()
        assert (await token(client, agent, settings.inventory_api_audience)).status_code == 401


@pytest.mark.asyncio
async def test_sdk_dependency_denies_missing_and_insufficient_scope(settings):
    async with client_for(settings) as (iam_app, iam_client):
        agent = await register(iam_client, ["inventory:read"])
        access_token = (await token(iam_client, agent, settings.inventory_api_audience)).json()[
            "access_token"
        ]
        verifier = AegentSecVerifier(
            settings.iam_issuer,
            settings.inventory_api_audience,
            f"{settings.iam_issuer}/.well-known/jwks.json",
        )

        async def key(_kid):
            return iam_app.state.tokens.jwks()["keys"][0]

        verifier._key = key
        api = FastAPI()
        require_purchase = verifier.require_scope("purchase:create")

        @api.post("/purchase-orders")
        async def purchase(identity: Annotated[AgentIdentity, Depends(require_purchase)]):
            return {"created": True}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url=settings.inventory_api_audience
        ) as client:
            assert (await client.post("/purchase-orders")).status_code == 401
            assert (
                await client.post(
                    "/purchase-orders", headers={"Authorization": f"Bearer {access_token}"}
                )
            ).status_code == 403
            wrong_audience = (await token(iam_client, agent, settings.mcp_resource_uri)).json()[
                "access_token"
            ]
            assert (
                await client.post(
                    "/purchase-orders", headers={"Authorization": f"Bearer {wrong_audience}"}
                )
            ).status_code == 401


@pytest.mark.asyncio
async def test_jwt_rejects_expiry_issuer_signature_and_algorithm(settings):
    async with client_for(settings) as (app, client):
        agent = await register(client, ["inventory:read"])
        good = (await token(client, agent, settings.inventory_api_audience)).json()["access_token"]
        claims = jwt.decode(good, options={"verify_signature": False})
        service = app.state.tokens

        def signed(payload, key=None, algorithm="RS256"):
            return jwt.encode(
                payload,
                key or service.private_key,
                algorithm=algorithm,
                headers={"kid": settings.iam_key_id},
            )

        with pytest.raises(jwt.ExpiredSignatureError):
            service.verify(
                signed(dict(claims, exp=datetime.now(UTC) - timedelta(seconds=1))),
                settings.inventory_api_audience,
            )
        with pytest.raises(jwt.InvalidIssuerError):
            service.verify(
                signed(dict(claims, iss="http://other-issuer")), settings.inventory_api_audience
            )
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with pytest.raises(jwt.InvalidSignatureError):
            service.verify(signed(claims, key=other_key), settings.inventory_api_audience)
        with pytest.raises(jwt.InvalidTokenError):
            service.verify(
                signed(claims, key="test-key" * 8, algorithm="HS256"),
                settings.inventory_api_audience,
            )


@pytest.mark.asyncio
async def test_mcp_authentication_over_real_http(settings):
    with socket.socket() as port_probe:
        port_probe.bind(("127.0.0.1", 0))
        port = port_probe.getsockname()[1]
    settings.iam_issuer = f"http://127.0.0.1:{port}"
    settings.mcp_resource_uri = f"{settings.iam_issuer}/mcp"
    app = create_app(settings)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    server_task = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.02)
        assert server.started
        async with httpx.AsyncClient(base_url=settings.iam_issuer, timeout=5) as client:
            body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
            headers = {"Accept": "application/json, text/event-stream"}
            assert (await client.post("/mcp/", json=body, headers=headers)).status_code == 401
            agent = await register(client, ["inventory:read"])
            bearer = (await token(client, agent, settings.mcp_resource_uri)).json()["access_token"]
            response = await client.post(
                "/mcp/",
                json=body,
                headers={**headers, "Authorization": f"Bearer {bearer}"},
            )
            assert response.status_code == 200
            names = {item["name"] for item in response.json()["result"]["tools"]}
            assert names == {"whoami", "check_permission", "list_my_permissions"}
    finally:
        server.should_exit = True
        await server_task


@pytest.mark.asyncio
async def test_admin_key_must_be_strong(settings):
    for weak in ("", "short", "replace-with-a-long-random-value"):
        with pytest.raises(ValueError):
            create_app(settings.model_copy(update={"admin_api_key": weak}))


@pytest.mark.asyncio
async def test_token_endpoint_rules_and_no_store_headers(settings):
    async with client_for(settings) as (_app, client):
        agent = await register(client, ["inventory:read", "purchase:create"])
        audience = settings.inventory_api_audience
        ok = await token(client, agent, audience, "inventory:read")
        assert ok.status_code == 200
        assert ok.headers["cache-control"] == "no-store"
        assert ok.json()["scope"] == "inventory:read"
        form = {"grant_type": "password", "resource": audience}
        auth = (agent["client_id"], agent["client_secret"])
        assert (await client.post("/api/v1/auth/token", auth=auth, data=form)).json() == {
            "error": "unsupported_grant_type"
        }
        malformed = await client.post(
            "/api/v1/auth/token",
            headers={"Authorization": "Basic !!!not-base64"},
            data={"grant_type": "client_credentials", "resource": audience},
        )
        assert malformed.status_code == 401
        unknown = dict(agent, client_id="cli_unknown")
        assert (await token(client, unknown, audience)).status_code == 401


@pytest.mark.asyncio
async def test_admin_can_deactivate_and_reactivate_agent(settings):
    async with client_for(settings) as (_app, client):
        agent = await register(client, ["inventory:read"])
        audience = settings.inventory_api_audience
        path = f"/api/v1/agents/{agent['agent_id']}"
        assert (await client.post(f"{path}/deactivate")).status_code == 401
        headers = {"X-Admin-Api-Key": ADMIN_KEY}
        assert (await client.post(f"{path}/deactivate", headers=headers)).json() == {
            "agent_id": agent["agent_id"],
            "is_active": False,
        }
        assert (await token(client, agent, audience)).status_code == 401
        assert (await client.post(f"{path}/activate", headers=headers)).status_code == 200
        assert (await token(client, agent, audience)).status_code == 200
        missing = await client.post("/api/v1/agents/agt_missing/deactivate", headers=headers)
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_deactivated_enterprise_blocks_agents_and_mcp_tokens(settings):
    async with client_for(settings) as (app, client):
        agent = await register(client, ["inventory:read"])
        mcp_token = (await token(client, agent, settings.mcp_resource_uri)).json()["access_token"]
        verifier = app.state.iam
        assert await verifier.active_agent(agent["agent_id"]) is not None
        headers = {"X-Admin-Api-Key": ADMIN_KEY}
        path = f"/api/v1/enterprises/{agent['enterprise_id']}/deactivate"
        assert (await client.post(path, headers=headers)).status_code == 200
        assert await verifier.active_agent(agent["agent_id"]) is None
        assert (await token(client, agent, settings.mcp_resource_uri)).status_code == 401
        assert mcp_token  # issued before deactivation; MCP verification now rejects it


@pytest.mark.asyncio
async def test_audit_log_records_events_without_secrets(settings):
    async with client_for(settings) as (_app, client):
        agent = await register(client, ["inventory:read"])
        audience = settings.inventory_api_audience
        await token(client, agent, audience)
        await token(client, agent, audience, "purchase:create")
        await token(client, dict(agent, client_secret="wrong"), audience)
        headers = {"X-Admin-Api-Key": ADMIN_KEY}
        await client.post(f"/api/v1/agents/{agent['agent_id']}/deactivate", headers=headers)
        assert (await client.get("/api/v1/audit")).status_code == 401
        response = await client.get("/api/v1/audit", headers=headers)
        events = response.json()["events"]
        kinds = [event["event_type"] for event in events]
        assert kinds == [
            "agent_deactivated",
            "token_denied",
            "token_denied",
            "token_issued",
            "agent_registered",
            "enterprise_registered",
        ]
        assert agent["client_secret"] not in response.text
        assert "access_token" not in response.text


@pytest.mark.asyncio
async def test_unknown_kid_jwks_refetch_is_rate_limited():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"keys": []})

    verifier = AegentSecVerifier("iss", "aud", "http://iam/jwks", min_refetch_seconds=60)
    verifier._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    for kid in ("a", "b", "c"):
        with pytest.raises(TokenVerificationError):
            await verifier._key(kid)
    assert calls == 1
    await verifier.aclose()


@pytest.mark.asyncio
async def test_scope_catalogue_is_managed_by_admin(settings):
    async with client_for(settings) as (_app, client):
        headers = {"X-Admin-Api-Key": ADMIN_KEY}
        assert (await client.get("/api/v1/scopes")).status_code == 401
        listed = (await client.get("/api/v1/scopes", headers=headers)).json()["scopes"]
        assert "inventory:read" in {row["scope"] for row in listed}
        for bad in ("ticket:*", "Ticket:create", "ticket", "ticket:create:now", "*"):
            response = await client.post("/api/v1/scopes", json={"scope": bad}, headers=headers)
            assert response.status_code == 422, bad
        created = await client.post(
            "/api/v1/scopes",
            json={"scope": "ticket:create", "description": "Tickets"},
            headers=headers,
        )
        assert created.status_code == 201
        duplicate = await client.post(
            "/api/v1/scopes", json={"scope": "ticket:create"}, headers=headers
        )
        assert duplicate.status_code == 409
        agent = await register(client, ["ticket:create"])
        audience = settings.inventory_api_audience
        assert (await token(client, agent, audience)).json()["scope"] == "ticket:create"
        in_use = await client.delete("/api/v1/scopes/ticket:create", headers=headers)
        assert (in_use.status_code, in_use.json()["detail"]) == (409, "scope_in_use")
        missing = await client.delete("/api/v1/scopes/nothing:here", headers=headers)
        assert missing.status_code == 404
        unused = await client.post("/api/v1/scopes", json={"scope": "report:read"}, headers=headers)
        assert unused.status_code == 201
        assert (
            await client.delete("/api/v1/scopes/report:read", headers=headers)
        ).status_code == 200
        names = (await client.get("/.well-known/oauth-authorization-server")).json()
        assert "ticket:create" in names["scopes_supported"]
        assert "report:read" not in names["scopes_supported"]
        events = (await client.get("/api/v1/audit", headers=headers)).json()["events"]
        assert {"scope_created", "scope_deleted"} <= {event["event_type"] for event in events}


@pytest.mark.asyncio
async def test_unknown_or_deleted_scope_cannot_be_granted(settings):
    async with client_for(settings) as (_app, client):
        headers = {"X-Admin-Api-Key": ADMIN_KEY}
        enterprise = await client.post(
            "/api/v1/enterprises", json={"name": "Acme"}, headers=headers
        )
        body = {
            "enterprise_id": enterprise.json()["enterprise_id"],
            "name": "Agent",
            "scopes": ["report:read"],
        }
        assert (await client.post("/api/v1/agents", json=body, headers=headers)).status_code == 400
        await client.post("/api/v1/scopes", json={"scope": "report:read"}, headers=headers)
        assert (await client.post("/api/v1/agents", json=body, headers=headers)).status_code == 201
