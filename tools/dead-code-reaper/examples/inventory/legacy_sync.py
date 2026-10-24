"""Sync with the old ERP system. The ERP was retired in 2024."""
import json


def sync_all(warehouse) -> str:
    return json.dumps({"synced": len(warehouse.items)})
