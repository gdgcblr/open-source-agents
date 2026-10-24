"""Deterministic, no-LLM end-to-end demo against two running applications."""

import asyncio
import json
import os

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

IAM = os.getenv("IAM_ISSUER", "http://localhost:8000")
MCP = os.getenv("MCP_RESOURCE_URI", f"{IAM}/mcp")
API = os.getenv("INVENTORY_API_AUDIENCE", "http://localhost:8001")


async def main() -> None:
    admin = os.environ["ADMIN_API_KEY"]
    async with httpx.AsyncClient(timeout=10) as client:
        headers = {"X-Admin-Api-Key": admin}
        enterprise = await client.post(
            f"{IAM}/api/v1/enterprises", json={"name": "Demo Enterprise"}, headers=headers
        )
        enterprise.raise_for_status()
        enterprise_id = enterprise.json()["enterprise_id"]
        agents = {}
        for name, scopes in (
            ("Inventory Agent", ["inventory:read"]),
            ("Purchase Agent", ["inventory:read", "purchase:create"]),
        ):
            response = await client.post(
                f"{IAM}/api/v1/agents",
                json={"enterprise_id": enterprise_id, "name": name, "scopes": scopes},
                headers=headers,
            )
            response.raise_for_status()
            agents[name] = response.json()

        async def token(agent: dict, resource: str) -> str:
            response = await client.post(
                f"{IAM}/api/v1/auth/token",
                auth=(agent["client_id"], agent["client_secret"]),
                data={"grant_type": "client_credentials", "resource": resource},
            )
            response.raise_for_status()
            return response.json()["access_token"]

        inventory = agents["Inventory Agent"]
        purchase = agents["Purchase Agent"]
        inventory_mcp = await token(inventory, MCP)
        inventory_api = await token(inventory, API)
        purchase_api = await token(purchase, API)

        async with (
            httpx.AsyncClient(
                headers={"Authorization": f"Bearer {inventory_mcp}"}, timeout=10
            ) as mcp_http,
            streamable_http_client(MCP, http_client=mcp_http) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            for name, arguments in (
                ("whoami", {}),
                ("check_permission", {"resource": "purchase", "action": "create"}),
                ("list_my_permissions", {}),
            ):
                result = await session.call_tool(name, arguments)
                print(name, result.structuredContent or json.loads(result.content[0].text))

        async def show(label: str, method: str, path: str, bearer: str) -> None:
            response = await client.request(
                method, f"{API}{path}", headers={"Authorization": f"Bearer {bearer}"}
            )
            print(label, response.status_code, response.json())

        await show("inventory read", "GET", "/inventory", inventory_api)
        await show("inventory purchase denied", "POST", "/purchase-orders", inventory_api)
        await show("purchase agent allowed", "POST", "/purchase-orders", purchase_api)
        await show("wrong audience denied", "GET", "/inventory", inventory_mcp)
        await show("invalid token denied", "GET", "/inventory", "invalid")

        print("--- administrator adds a new scope with no code change ---")
        created = await client.post(
            f"{IAM}/api/v1/scopes",
            json={"scope": "ticket:create", "description": "Open support tickets"},
            headers=headers,
        )
        print("create scope ticket:create", created.status_code)  # 409 on later runs
        helper = await client.post(
            f"{IAM}/api/v1/agents",
            json={
                "enterprise_id": enterprise_id,
                "name": "Ticket Agent",
                "scopes": ["ticket:create"],
            },
            headers=headers,
        )
        helper.raise_for_status()
        ticket_token = await client.post(
            f"{IAM}/api/v1/auth/token",
            auth=(helper.json()["client_id"], helper.json()["client_secret"]),
            data={"grant_type": "client_credentials", "resource": API},
        )
        print("ticket agent token scope", ticket_token.json()["scope"])
        unknown = await client.post(
            f"{IAM}/api/v1/agents",
            json={"enterprise_id": enterprise_id, "name": "Rogue", "scopes": ["ticket:*"]},
            headers=headers,
        )
        print("wildcard scope registration denied", unknown.status_code)

        print("--- administrator deactivates the Inventory Agent ---")
        revoke = await client.post(
            f"{IAM}/api/v1/agents/{inventory['agent_id']}/deactivate", headers=headers
        )
        revoke.raise_for_status()
        mcp_after = await client.post(
            f"{MCP}/", headers={"Authorization": f"Bearer {inventory_mcp}"}, json={}
        )
        print("deactivated agent, existing MCP token", mcp_after.status_code)
        new_token = await client.post(
            f"{IAM}/api/v1/auth/token",
            auth=(inventory["client_id"], inventory["client_secret"]),
            data={"grant_type": "client_credentials", "resource": API},
        )
        print("deactivated agent, new token request", new_token.status_code)
        # The SDK verifies signed claims offline, so an already issued API token stays valid
        # until it expires. Short token lifetimes (JWT_EXPIRATION_MINUTES) bound this window.
        await show(
            "deactivated agent, old API token (valid until expiry)",
            "GET",
            "/inventory",
            inventory_api,
        )

        print("--- audit log (newest first) ---")
        audit = await client.get(f"{IAM}/api/v1/audit", params={"limit": 12}, headers=headers)
        audit.raise_for_status()
        for event in audit.json()["events"]:
            print(event["created_at"], event["event_type"], event["agent_id"], event["detail"])


if __name__ == "__main__":
    asyncio.run(main())
