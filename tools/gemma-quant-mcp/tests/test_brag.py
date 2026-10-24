import pytest
from core.brag_tool import generate_arthaniti_brag_sheet

def test_arthaniti_brag_sheet():
    sheet = generate_arthaniti_brag_sheet()
    assert sheet["project"] == "Arthaniti Quant Hub & MCP Engine"
    assert sheet["hub_urn"] == "urn:adk:hub:arthaniti-quant-master"
    assert len(sheet["achievements"]) >= 5
    assert sheet["benchmarks"]["pivot_latency_ms"] < 2.0
    assert "gemini-2.5-flash" in sheet["supported_models"]
