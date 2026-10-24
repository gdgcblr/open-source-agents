"""Export a warehouse in different formats."""
import json


def export(warehouse, fmt: str) -> str:
    return globals()["export_" + fmt](warehouse)


def export_json(warehouse) -> str:
    return json.dumps([i.to_dict() for i in warehouse.items])


def export_xml(warehouse) -> str:
    rows = "".join(f"<item name='{i.name}' qty='{i.qty}'/>" for i in warehouse.items)
    return f"<items>{rows}</items>"
