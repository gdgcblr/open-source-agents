"""Sample data used by the test suite."""
from .models import Item, Warehouse


def make_sample_warehouse() -> Warehouse:
    wh = Warehouse()
    wh.add(Item("bolt", 100, 0.25))
    wh.add(Item("nut", 250, 0.1))
    return wh


def make_big_warehouse(n: int) -> Warehouse:
    wh = Warehouse()
    for i in range(n):
        wh.add(Item(f"part-{i}", i, 1.0))
    return wh
