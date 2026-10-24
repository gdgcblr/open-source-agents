from fastapi import APIRouter

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
async def health() -> dict[str, str]:
    """Liveness probe used by Docker and load balancers."""
    return {"status": "ok"}
