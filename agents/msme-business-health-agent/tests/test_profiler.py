import os
import subprocess
import sys

import pytest

from src.clean import clean_sheet
from src.ingest import load_xlsx
from src.profiler import build_overview

WB = os.path.join("data", "sample_workbook.xlsx")


@pytest.fixture(scope="session", autouse=True)
def workbook():
    if not os.path.exists(WB):
        subprocess.check_call([sys.executable, "scripts/make_sample_workbook.py"])
    return WB


def _sheets():
    return {n: clean_sheet(d) for n, d in load_xlsx(WB).items()}


def test_header_detected_and_totals_removed():
    sales = _sheets()["Sales"]
    assert list(sales.columns)[:3] == ["Date", "Invoice No", "Customer"]
    assert not sales["Date"].astype(str).str.lower().str.startswith("total").any()
    assert len(sales) == 63  # 60 rows + 3 duplicates, totals row removed


def test_overview_counts_and_quality():
    ov = build_overview(_sheets())
    assert ov["workbook_summary"]["sheets"] == 4
    sales = next(s for s in ov["sheets"] if s["name"] == "Sales")
    assert sales["data_quality"]["duplicate_rows"] >= 3
    assert sales["data_quality"]["missing_pct"] > 0
    assert sales["date_columns"]["Date"]["invalid_count"] >= 1


def test_departments_guessed():
    ov = build_overview(_sheets())
    depts = {s["name"]: s["department"] for s in ov["sheets"]}
    assert depts["Sales"] == "Sales"
    assert depts["Inventory"] == "Inventory"
    assert depts["Support Tickets"] == "Support"
