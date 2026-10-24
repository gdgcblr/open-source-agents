import base64
import binascii
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from aegentsec.services import SCOPE_PATTERN, IAMService, ServiceError


class EnterpriseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class AgentCreate(BaseModel):
    enterprise_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=200)
    scopes: list[str]


class ScopeCreate(BaseModel):
    scope: str = Field(pattern=SCOPE_PATTERN, max_length=100)
    description: str = Field(default="", max_length=500)


router = APIRouter()


def invalid_client() -> JSONResponse:
    return JSONResponse(
        {"error": "invalid_client"},
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="aegentsec"'},
    )


def iam(request: Request) -> IAMService:
    return request.app.state.iam


def require_admin(
    request: Request, x_admin_api_key: Annotated[str | None, Header()] = None
) -> None:
    expected = request.app.state.settings.admin_api_key
    if not expected or not x_admin_api_key or not secrets.compare_digest(x_admin_api_key, expected):
        raise HTTPException(401, "Administrator API key required")


@router.post("/api/v1/enterprises", status_code=201, dependencies=[Depends(require_admin)])
async def register_enterprise(body: EnterpriseCreate, service: Annotated[IAMService, Depends(iam)]):
    return await service.register_enterprise(body.name)


@router.post("/api/v1/agents", status_code=201, dependencies=[Depends(require_admin)])
async def register_agent(body: AgentCreate, service: Annotated[IAMService, Depends(iam)]):
    try:
        return await service.register_agent(body.enterprise_id, body.name, body.scopes)
    except ServiceError as exc:
        raise HTTPException(exc.status, exc.code) from exc


async def _set_active(call, ident: str, active: bool):
    try:
        return await call(ident, active)
    except ServiceError as exc:
        raise HTTPException(exc.status, exc.code) from exc


@router.post("/api/v1/agents/{agent_id}/deactivate", dependencies=[Depends(require_admin)])
async def deactivate_agent(agent_id: str, service: Annotated[IAMService, Depends(iam)]):
    return await _set_active(service.set_agent_active, agent_id, False)


@router.post("/api/v1/agents/{agent_id}/activate", dependencies=[Depends(require_admin)])
async def activate_agent(agent_id: str, service: Annotated[IAMService, Depends(iam)]):
    return await _set_active(service.set_agent_active, agent_id, True)


@router.post(
    "/api/v1/enterprises/{enterprise_id}/deactivate", dependencies=[Depends(require_admin)]
)
async def deactivate_enterprise(enterprise_id: str, service: Annotated[IAMService, Depends(iam)]):
    return await _set_active(service.set_enterprise_active, enterprise_id, False)


@router.post("/api/v1/enterprises/{enterprise_id}/activate", dependencies=[Depends(require_admin)])
async def activate_enterprise(enterprise_id: str, service: Annotated[IAMService, Depends(iam)]):
    return await _set_active(service.set_enterprise_active, enterprise_id, True)


@router.post("/api/v1/scopes", status_code=201, dependencies=[Depends(require_admin)])
async def create_scope(body: ScopeCreate, service: Annotated[IAMService, Depends(iam)]):
    try:
        return await service.create_scope(body.scope, body.description)
    except ServiceError as exc:
        raise HTTPException(exc.status, exc.code) from exc


@router.get("/api/v1/scopes", dependencies=[Depends(require_admin)])
async def list_scopes(service: Annotated[IAMService, Depends(iam)]):
    return {"scopes": await service.db.list_scopes()}


@router.delete("/api/v1/scopes/{scope}", dependencies=[Depends(require_admin)])
async def delete_scope(scope: str, service: Annotated[IAMService, Depends(iam)]):
    try:
        return await service.delete_scope(scope)
    except ServiceError as exc:
        raise HTTPException(exc.status, exc.code) from exc


@router.get("/api/v1/audit", dependencies=[Depends(require_admin)])
async def audit_log(service: Annotated[IAMService, Depends(iam)], limit: int = 50):
    return {"events": await service.audit_events(limit)}


@router.post("/api/v1/auth/token")
async def issue_token(
    request: Request,
    grant_type: Annotated[str, Form()],
    resource: Annotated[str, Form()],
    scope: Annotated[str, Form()] = "",
):
    service = request.app.state.iam
    if grant_type != "client_credentials":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
    if resource not in request.app.state.settings.allowed_audiences:
        return JSONResponse({"error": "invalid_target"}, status_code=400)
    basic = request.headers.get("authorization", "")
    if not basic.lower().startswith("basic "):
        return invalid_client()
    try:
        credentials = base64.b64decode(basic[6:], validate=True).decode()
        client_id, secret = credentials.split(":", 1)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return invalid_client()
    try:
        agent = await service.authenticate(client_id, secret)
    except ServiceError:
        await service.audit("token_denied", reason="invalid_client", client_id=client_id[:100])
        return invalid_client()
    requested = scope.split() if scope else agent["scopes"]
    try:
        granted = await service.validate_scopes(requested)
        if not set(granted).issubset(set(agent["scopes"])):
            raise ServiceError("invalid_scope")
    except ServiceError:
        await service.audit(
            "token_denied",
            agent_id=agent["agent_id"],
            enterprise_id=agent["enterprise_id"],
            reason="invalid_scope",
            requested=requested[:20],
        )
        return JSONResponse({"error": "invalid_scope"}, status_code=400)
    settings = request.app.state.settings
    await service.audit(
        "token_issued",
        agent_id=agent["agent_id"],
        enterprise_id=agent["enterprise_id"],
        resource=resource,
        scopes=granted,
    )
    return JSONResponse(
        {
            "access_token": request.app.state.tokens.issue(agent, granted, resource),
            "token_type": "Bearer",
            "expires_in": settings.jwt_expiration_minutes * 60,
            "scope": " ".join(granted),
        },
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
