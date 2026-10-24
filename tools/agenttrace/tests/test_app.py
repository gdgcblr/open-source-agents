"""Tests for AgentTrace Streamlit application helpers."""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import load_example
from analyzer import analyze_trace


def test_load_example_clean_trace():
    """Verify load_example successfully loads clean_trace.json."""
    content = load_example("clean_trace.json")
    assert content
    data = json.loads(content)
    assert data["name"] == "Synthetic Clean Agent Trace Demo"
    report = analyze_trace(data)
    assert report["finding_count"] == 1
    assert report["findings"][0]["severity"] == "Info"


def test_load_example_failed_trace():
    """Verify load_example successfully loads failed_trace.json."""
    content = load_example("failed_trace.json")
    assert content
    data = json.loads(content)
    assert data["name"] == "Synthetic Failed Agent Trace Demo"
    report = analyze_trace(data)
    assert report["finding_count"] == 4
    severities = [f["severity"] for f in report["findings"]]
    assert severities == ["Critical", "High", "Medium", "Medium"]


def test_load_example_missing_file():
    """Verify load_example returns empty string on missing file."""
    content = load_example("does_not_exist.json")
    assert content == ""
