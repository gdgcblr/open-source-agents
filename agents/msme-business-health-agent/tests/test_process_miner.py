import os

import pytest

from src.clean import clean_sheet
from src.ingest import load_xlsx
from src.process_miner import detect_event_log, mine_process

WB = os.path.join("data", "sample_workbook.xlsx")


@pytest.fixture(scope="module")
def sheets():
    return {n: clean_sheet(d) for n, d in load_xlsx(WB).items()}


def test_only_order_events_is_an_event_log(sheets):
    found = {n: detect_event_log(d) for n, d in sheets.items()}
    assert found["Order Events"] is not None
    assert found["Sales"] is None
    assert found["Inventory"] is None


def test_planted_bottleneck_is_ranked_first(sheets):
    df = sheets["Order Events"]
    result = mine_process(df, detect_event_log(df))
    top = result["top_bottlenecks"][0]
    assert top["transition"] == "Packed -> Dispatched"
    assert top["avg_hours"] > 20
    assert result["cases"] == 30
    assert result["process_variants"][0]["pct"] == 100.0
