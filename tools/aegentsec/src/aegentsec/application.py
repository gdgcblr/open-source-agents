from contextlib import asynccontextmanager

from fastapi import FastAPI

from aegentsec.api import router
from aegentsec.config import Settings
from aegentsec.database import Database
from aegentsec.mcp_server import build_mcp
from aegentsec.services import IAMService
from aegentsec.tokens import TokenService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.validate_admin_api_key()
    db = Database(settings.database_path)
    iam = IAMService(db)
    tokens = TokenService(settings)
    mcp = build_mcp(settings, tokens, iam)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await db.connect()
        async with mcp.session_manager.run():
            yield
        await db.close()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.state.iam = iam
    app.state.tokens = tokens
    app.include_router(router)

    @app.get("/.well-known/jwks.json")
    def jwks():
        return tokens.jwks()

    @app.get("/.well-known/oauth-authorization-server")
    async def authorization_server_metadata():
        return {
            "issuer": settings.iam_issuer,
            "token_endpoint": f"{settings.iam_issuer}/api/v1/auth/token",
            "jwks_uri": f"{settings.iam_issuer}/.well-known/jwks.json",
            "grant_types_supported": ["client_credentials"],
            "response_types_supported": [],
            "token_endpoint_auth_methods_supported": ["client_secret_basic"],
            "scopes_supported": sorted(await iam.scope_names()),
        }

    @app.get("/.well-known/oauth-protected-resource/mcp")
    async def resource_metadata():
        return {
            "resource": settings.mcp_resource_uri,
            "authorization_servers": [settings.iam_issuer],
            "bearer_methods_supported": ["header"],
            "scopes_supported": sorted(await iam.scope_names()),
        }

    app.mount("/mcp", mcp.streamable_http_app())
    return app
