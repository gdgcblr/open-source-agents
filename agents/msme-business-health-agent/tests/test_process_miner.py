import os
import pandas as pd
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


def test_root_cause_diagnostics_and_metadata(sheets):
    df = sheets["Order Events"]
    result = mine_process(df, detect_event_log(df))
    diagnostics = result.get("root_cause_diagnostics")
    assert diagnostics is not None
    assert diagnostics["primary_bottleneck"] == "Packed -> Dispatched"
    assert "Packed" in diagnostics["root_cause_hypothesis"]
    assert "Dispatched" in diagnostics["root_cause_hypothesis"]


def test_financial_leak_quantification(sheets):
    df = sheets["Order Events"]
    result = mine_process(df, detect_event_log(df))
    leak = result.get("financial_leak")
    assert leak is not None
    assert leak["labor_holding_loss_usd"] > 0
    assert leak["churn_cancellation_risk_usd"] > 0
    assert leak["total_financial_leak_usd"] == round(
        leak["labor_holding_loss_usd"] + leak["churn_cancellation_risk_usd"], 2
    )


def test_autonomous_remediation_and_transparency(sheets):
    df = sheets["Order Events"]
    result = mine_process(df, detect_event_log(df))
    fix = result.get("autonomous_remediation")
    assert fix is not None
    assert "Webhook" in fix["title"] or "Approval" in fix["title"]
    assert fix["projected_idle_reduction_pct"] > 80.0

    msg = result.get("transparency_action")
    assert msg is not None
    assert "Dear Customer" in msg["customer_message"]
    assert msg["compensation_offer"] is not None


def test_apa_strict_json_schema(sheets):
    df = sheets["Order Events"]
    result = mine_process(df, detect_event_log(df))
    apa = result.get("apa_output_json")
    assert apa is not None

    required_keys = [
        "chain_of_thought_reasoning",
        "department_bottleneck",
        "exact_metric_leak",
        "root_cause_analysis",
        "business_acceleration_fix",
        "transparency_action_executed",
    ]
    for key in required_keys:
        assert key in apa, f"Missing required APA key: {key}"
        assert isinstance(apa[key], str) and len(apa[key].strip()) > 0


def test_weekend_stall_root_cause_hypothesis():
    # Synthetic weekend-stalled log: events queued Saturday / Sunday
    # Sept 19, 2026 is Saturday; Sept 20, 2026 is Sunday; Sept 21, 2026 is Monday
    data = {
        "case_id": ["C1", "C1", "C2", "C2", "C3", "C3"],
        "activity": ["Checkout", "Fulfillment", "Checkout", "Fulfillment", "Checkout", "Fulfillment"],
        "timestamp": [
            "2026-09-19 20:00:00",
            "2026-09-21 10:00:00",
            "2026-09-19 21:00:00",
            "2026-09-21 11:00:00",
            "2026-09-20 09:00:00",
            "2026-09-21 14:00:00",
        ],
        "amount": [250.0, 250.0, 320.0, 320.0, 180.0, 180.0],
    }
    df = pd.DataFrame(data)
    cols = detect_event_log(df)
    assert cols is not None

    result = mine_process(df, cols, idle_threshold_hours=12.0)
    top = result["top_bottlenecks"][0]
    assert top["weekend_start_pct"] == 100.0
    assert "weekend" in result["root_cause_diagnostics"]["root_cause_hypothesis"].lower()
