
import uuid

import httpx
import pytest
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse


# --------------------------------------------------
# Service B: downstream service
# --------------------------------------------------

service_b = FastAPI()


@service_b.get("/inventory/{product_id}")
async def get_inventory(
    product_id: int,
    x_trace_id: str | None = Header(default=None),
):
    trace_id = x_trace_id or "missing-trace-id"

    # Simulate a real downstream failure.
    return JSONResponse(
        status_code=500,
        content={
            "service": "service-b",
            "trace_id": trace_id,
            "error_type": "InventoryDatabaseError",
            "message": "Inventory database connection failed",
            "product_id": product_id,
        },
    )


# --------------------------------------------------
# Service A: calls Service B
# --------------------------------------------------

service_a = FastAPI()


@service_a.get("/orders/{product_id}")
async def get_order(
    product_id: int,
    request: Request,
):
    trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())

    # Propagate the trace ID to Service B.
    transport = httpx.ASGITransport(app=service_b)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://service-b",
    ) as client:
        response = await client.get(
            f"/inventory/{product_id}",
            headers={"X-Trace-ID": trace_id},
        )

    if response.status_code >= 500:
        downstream_error = response.json()

        raise HTTPException(
            status_code=502,
            detail={
                "service": "service-a",
                "trace_id": trace_id,
                "message": "Downstream service failed",
                "downstream_error": downstream_error,
            },
        )

    return response.json()


# --------------------------------------------------
# Test: verify downstream failure identification
# --------------------------------------------------

@pytest.mark.asyncio
async def test_service_b_failure_through_service_a():
    trace_id = str(uuid.uuid4())

    transport = httpx.ASGITransport(app=service_a)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://service-a",
    ) as client:
        response = await client.get(
            "/orders/101",
            headers={"X-Trace-ID": trace_id},
        )

    # Service B's 500 becomes Service A's 502.
    assert response.status_code == 502

    body = response.json()
    details = body["detail"]
    downstream = details["downstream_error"]

    # The same ID must flow through both services.
    assert details["trace_id"] == trace_id
    assert downstream["trace_id"] == trace_id

    # Identify the actual downstream cause.
    assert downstream["service"] == "service-b"
    assert downstream["error_type"] == "InventoryDatabaseError"
    assert "database connection failed" in downstream["message"].lower()

    print("\nDistributed failure detected")
    print(f"Trace ID: {trace_id}")
    print("Service A: HTTP 502")
    print("Service B: HTTP 500")
    print(f"Root cause: {downstream['error_type']}")
    print(f"Details: {downstream['message']}")
