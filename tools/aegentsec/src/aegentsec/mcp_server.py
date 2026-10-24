import jwt
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

from aegentsec.config import Settings
from aegentsec.services import IAMService, has_permission
from aegentsec.tokens import TokenService


class AgentTokenVerifier:
    def __init__(self, settings: Settings, tokens: TokenService, iam: IAMService):
        self.settings = settings
        self.tokens = tokens
        self.iam = iam

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = self.tokens.verify(token, self.settings.mcp_resource_uri)
        except jwt.PyJWTError:
            return None
        agent = await self.iam.active_agent(claims["sub"])
        if agent is None or agent["client_id"] != claims["client_id"]:
            return None
        if agent["enterprise_id"] != claims["enterprise_id"]:
            return None
        scopes = claims.get("scope", "").split()
        if not set(scopes).issubset(set(agent["scopes"])):
            return None
        return AccessToken(
            token=token,
            client_id=agent["client_id"],
            scopes=scopes,
            expires_at=claims["exp"],
            resource=self.settings.mcp_resource_uri,
            subject=agent["agent_id"],
            claims={"enterprise_id": agent["enterprise_id"], "agent_name": agent["name"]},
        )


def build_mcp(settings: Settings, tokens: TokenService, iam: IAMService) -> FastMCP:
    server = FastMCP(
        "AegentSec",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        token_verifier=AgentTokenVerifier(settings, tokens, iam),
        auth=AuthSettings(
            issuer_url=settings.iam_issuer,
            resource_server_url=settings.mcp_resource_uri,
            required_scopes=[],
            validate_token_resource=True,
        ),
    )

    def current() -> AccessToken:
        identity = get_access_token()
        if identity is None or identity.subject is None:
            raise PermissionError("Authenticated MCP request required")
        return identity

    @server.tool()
    async def whoami() -> dict:
        """Return the authenticated agent's identity."""
        identity = current()
        return {
            "agent_id": identity.subject,
            "enterprise_id": identity.claims["enterprise_id"],
            "agent_name": identity.claims["agent_name"],
            "status": "active",
        }

    @server.tool()
    async def check_permission(resource: str, action: str) -> dict:
        """Check the caller's granted scopes; never perform the requested action."""
        identity = current()
        required_scope = f"{resource}:{action}"
        allowed = has_permission(set(identity.scopes), required_scope, await iam.scope_names())
        return {
            "allowed": allowed,
            "resource": resource,
            "action": action,
            "required_scope": required_scope,
            "reason": "Required permission is present"
            if allowed
            else "Required permission is absent",
        }

    @server.tool()
    async def list_my_permissions() -> dict:
        """List only the authenticated agent's permissions."""
        identity = current()
        return {"agent_id": identity.subject, "scopes": sorted(identity.scopes)}

    return server
