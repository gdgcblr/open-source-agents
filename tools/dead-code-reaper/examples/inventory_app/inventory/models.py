"""Items and warehouses."""
import csv
import io
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Item:
    name: str
    qty: int
    unit_price: float

    def total_value(self) -> float:
        return self.qty * self.unit_price

    def to_dict(self) -> dict:
        return {"name": self.name, "qty": self.qty, "unit_price": self.unit_price}

    def _debug_repr(self) -> str:
        return f"<Item {self.name} x{self.qty}>"


@dataclass
class Warehouse:
    items: List[Item] = field(default_factory=list)

    def add(self, item: Item) -> None:
        self.items.append(item)

    def find(self, name: str) -> Optional[Item]:
        return next((i for i in self.items if i.name == name), None)

    def restock(self, name: str, qty: int) -> None:
        item = self.find(name)
        if item is None:
            raise KeyError(name)
        item.qty += qty

    # Old CSV export, replaced by inventory.exporters.
    def legacy_export_csv(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        for item in self.items:
            writer.writerow([item.name, item.qty])
        return buf.getvalue()
