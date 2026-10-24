"""FastAPI adapters for the framework-independent JWT verifier."""

from fastapi import HTTPException, Request

from aegentsec_sdk.verifier import AegentSecVerifier, AgentIdentity, TokenVerificationError


def require_scope(verifier: AegentSecVerifier, required_scope: str):
    async def dependency(request: Request) -> AgentIdentity:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            raise HTTPException(401, "Bearer token required")
        try:
            identity = await verifier.verify(header[7:])
        except TokenVerificationError as exc:
            raise HTTPException(401, str(exc)) from exc
        if required_scope not in identity.scopes:
            raise HTTPException(403, "Insufficient scope")
        return identity

    return dependency
