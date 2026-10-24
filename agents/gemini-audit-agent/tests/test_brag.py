import pytest
from core.brag_tool import generate_bharat_dues_brag_sheet

def test_bharat_dues_brag_sheet():
    sheet = generate_bharat_dues_brag_sheet()
    assert sheet["project"] == "Bharat Dues AI Audit Agent"
    assert sheet["hub_urn"] == "urn:adk:hub:bharat-dues-master"
    assert len(sheet["achievements"]) >= 5
    assert sheet["benchmarks"]["audit_latency_ms"] < 5.0
    assert "gemini-2.5-flash" in sheet["supported_models"]
