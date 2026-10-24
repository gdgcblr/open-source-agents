"""Mock enterprise API protected independently by the AegentSec SDK."""

import os
from typing import Annotated

from aegentsec_sdk import AegentSecVerifier, AgentIdentity
from fastapi import Depends, FastAPI

issuer = os.getenv("IAM_ISSUER", "http://localhost:8000")
audience = os.getenv("INVENTORY_API_AUDIENCE", "http://localhost:8001")
auth = AegentSecVerifier(
    issuer=issuer,
    audience=audience,
    jwks_url=f"{issuer}/.well-known/jwks.json",
)
app = FastAPI(title="Protected inventory demo")
require_inventory_read = auth.require_scope("inventory:read")
require_purchase_create = auth.require_scope("purchase:create")
require_inventory_delete = auth.require_scope("inventory:delete")


@app.get("/inventory")
async def inventory(identity: Annotated[AgentIdentity, Depends(require_inventory_read)]):
    return {"material": "RM-1001", "quantity": 400}


@app.post("/purchase-orders")
async def purchase_order(identity: Annotated[AgentIdentity, Depends(require_purchase_create)]):
    return {"message": "Purchase order created successfully", "order_id": "PO-001"}


@app.delete("/inventory/{material_id}")
async def delete_inventory(
    material_id: str, identity: Annotated[AgentIdentity, Depends(require_inventory_delete)]
):
    return {"message": "Inventory record deleted"}
