import json
import os
import subprocess
import sys


def test_cli_overview_mode():
    cmd = [
        sys.executable,
        "-m",
        "src.main",
        "overview",
        "--file",
        os.path.join("data", "sample_workbook.xlsx"),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(res.stdout)
    assert "workbook_summary" in out
    assert "process_mining" in out
    assert out["process_mining"]["sheet"] == "Order Events"


def test_cli_process_xray_apa_json():
    cmd = [
        sys.executable,
        "-m",
        "src.main",
        "process-xray",
        "--file",
        os.path.join("data", "sample_workbook.xlsx"),
        "--apa-json",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(res.stdout)
    expected_keys = [
        "chain_of_thought_reasoning",
        "department_bottleneck",
        "exact_metric_leak",
        "root_cause_analysis",
        "business_acceleration_fix",
        "transparency_action_executed",
    ]
    for key in expected_keys:
        assert key in out
        assert len(out[key].strip()) > 0
