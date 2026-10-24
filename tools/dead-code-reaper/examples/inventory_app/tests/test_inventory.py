import json
from decimal import Decimal

from inventory import Item, Warehouse
from inventory.cli import main
from inventory.encoding import DecimalEncoder
from inventory.exporters import export
from inventory.pricing import apply_discount, calculate_tax, price_for
from inventory.reports import build_report
from inventory.sample_data import make_sample_warehouse


def test_item_value():
    assert Item("bolt", 4, 0.5).total_value() == 2.0


def test_restock():
    wh = make_sample_warehouse()
    wh.restock("bolt", 10)
    assert wh.find("bolt").qty == 110


def test_tax_and_discount():
    assert calculate_tax(100) == 18.0
    assert apply_discount(200, 10) == 180.0
    assert apply_discount(200, 0) == 200


def test_premium_pricing(monkeypatch):
    monkeypatch.setenv("PRICING_STRATEGY", "premium_pricing")
    assert price_for(Item("bolt", 1, 4.0)) == 5.0


def test_export_json():
    data = json.loads(export(make_sample_warehouse(), "json"))
    assert data[0]["name"] == "bolt"


def test_summary_report():
    assert build_report("summary", make_sample_warehouse()).startswith("2 items")


def test_decimal_encoder():
    assert json.dumps({"x": Decimal("1.5")}, cls=DecimalEncoder) == '{"x": 1.5}'


def test_cli(capsys):
    assert main(["summary"]) == 0
    assert "2 items" in capsys.readouterr().out


def test_big_warehouse():
    from inventory.sample_data import make_big_warehouse
    assert len(make_big_warehouse(5).items) == 5
