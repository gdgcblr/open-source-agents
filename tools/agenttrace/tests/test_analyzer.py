"""Tests for AgentTrace analyzer."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from analyzer import analyze_trace

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def test_repeated_identical_tool_calls_detected():
    """1. Repeated identical tool calls (>= 3) trigger a High severity finding."""
    trace = {
        "events": [
            {"id": "c1", "type": "tool_call", "tool": "search", "input": {"q": "python"}},
            {"id": "r1", "type": "tool_result", "call_id": "c1", "output": "ok"},
            {"id": "c2", "type": "tool_call", "tool": "search", "input": {"q": "python"}},
            {"id": "r2", "type": "tool_result", "call_id": "c2", "output": "ok"},
            {"id": "c3", "type": "tool_call", "tool": "search", "input": {"q": "python"}},
            {"id": "r3", "type": "tool_result", "call_id": "c3", "output": "ok"},
        ]
    }
    res = analyze_trace(trace)
    repeated_findings = [f for f in res["findings"] if f["severity"] == "High" and "Repeated" in f["title"]]
    assert len(repeated_findings) == 1
    assert "search" in repeated_findings[0]["title"]
    assert "3 times" in repeated_findings[0]["evidence"]


def test_explicit_error_event_detected():
    """2. Explicit error event is detected with Critical severity."""
    trace = {
        "events": [
            {"id": "e1", "type": "error", "error": "Fatal DB connection error"}
        ]
    }
    res = analyze_trace(trace)
    critical_findings = [f for f in res["findings"] if f["severity"] == "Critical"]
    assert len(critical_findings) == 1
    assert "Fatal DB connection error" in critical_findings[0]["evidence"]
    assert critical_findings[0]["event_id"] == "e1"


def test_error_event_without_details_is_high():
    """Error event with missing or empty error field emits High severity finding."""
    trace = {
        "events": [
            {"id": "e1", "type": "error", "error": ""}
        ]
    }
    res = analyze_trace(trace)
    high_findings = [f for f in res["findings"] if f["severity"] == "High" and "no details" in f["title"]]
    assert len(high_findings) == 1


def test_error_reported_on_non_error_event():
    """Error field on a non-error event emits High severity finding."""
    trace = {
        "events": [
            {"id": "c1", "type": "tool_call", "tool": "calc", "error": "Invalid syntax"}
        ]
    }
    res = analyze_trace(trace)
    findings = [f for f in res["findings"] if f["severity"] == "High" and "Error reported" in f["title"]]
    assert len(findings) == 1


def test_timeout_like_result_detected():
    """3. Timeout-like tool result text is detected as Medium severity."""
    trace = {
        "events": [
            {"id": "c1", "type": "tool_call", "tool": "api_fetch", "input": {"url": "https://api"}},
            {"id": "r1", "type": "tool_result", "call_id": "c1", "output": "Request timed out after 30s"}
        ]
    }
    res = analyze_trace(trace)
    timeout_findings = [f for f in res["findings"] if f["severity"] == "Medium" and "Timeout" in f["title"]]
    assert len(timeout_findings) == 1
    assert "timed out" in timeout_findings[0]["evidence"]


def test_completed_trace_with_missing_result_is_flagged():
    """4. Completed trace with unmatched tool call is flagged as Medium severity."""
    trace = {
        "complete": True,
        "events": [
            {"id": "c1", "type": "tool_call", "tool": "read_file", "input": {"path": "a.txt"}}
        ]
    }
    res = analyze_trace(trace)
    missing_findings = [f for f in res["findings"] if f["severity"] == "Medium" and "missing result" in f["title"].lower()]
    assert len(missing_findings) == 1
    assert missing_findings[0]["event_id"] == "c1"


def test_incomplete_trace_with_missing_result_is_not_flagged():
    """5. Incomplete trace (complete is False or omitted) does not flag missing results."""
    trace_omitted = {
        "events": [
            {"id": "c1", "type": "tool_call", "tool": "read_file", "input": {"path": "a.txt"}}
        ]
    }
    res_omitted = analyze_trace(trace_omitted)
    missing_omitted = [f for f in res_omitted["findings"] if "missing result" in f["title"].lower()]
    assert len(missing_omitted) == 0

    trace_false = {
        "complete": False,
        "events": [
            {"id": "c1", "type": "tool_call", "tool": "read_file", "input": {"path": "a.txt"}}
        ]
    }
    res_false = analyze_trace(trace_false)
    missing_false = [f for f in res_false["findings"] if "missing result" in f["title"].lower()]
    assert len(missing_false) == 0


def test_clean_trace_returns_one_informational_result():
    """6. Clean trace returns exactly one Info finding with specific wording."""
    clean_path = EXAMPLES_DIR / "clean_trace.json"
    with open(clean_path, "r", encoding="utf-8") as f:
        clean_trace = json.load(f)

    res = analyze_trace(clean_trace)
    assert res["finding_count"] == 1
    assert res["findings"][0]["severity"] == "Info"
    assert res["findings"][0]["title"] == "No known failure pattern detected"
    assert "not guarantee" in res["findings"][0]["recommendation"].lower()


def test_empty_events_array_does_not_crash():
    """7. Empty events array does not crash and returns Info finding."""
    res = analyze_trace({"events": []})
    assert res["event_count"] == 0
    assert res["finding_count"] == 1
    assert res["findings"][0]["severity"] == "Info"


def test_invalid_root_schema_raises_value_error():
    """8. Invalid root types or events array raise clear ValueError."""
    with pytest.raises(ValueError, match="JSON object"):
        analyze_trace(["not", "a", "dict"])  # type: ignore

    with pytest.raises(ValueError, match="'events' array"):
        analyze_trace({})

    with pytest.raises(ValueError, match="'events' must be an array"):
        analyze_trace({"events": "not a list"})

    with pytest.raises(ValueError, match="'name' must be a string"):
        analyze_trace({"name": 123, "events": []})

    with pytest.raises(ValueError, match="'complete' must be a boolean"):
        analyze_trace({"complete": "yes", "events": []})


def test_malformed_event_element_does_not_crash():
    """9. Non-object element in events array emits Medium finding and continues."""
    trace = {
        "events": [
            "invalid string event",
            {"id": "e1", "type": "error", "error": "Something broke"}
        ]
    }
    res = analyze_trace(trace)
    assert res["event_count"] == 2
    malformed = [f for f in res["findings"] if f["title"] == "Malformed event entry"]
    assert len(malformed) == 1
    assert "array index 0" in malformed[0]["evidence"]

    critical = [f for f in res["findings"] if f["severity"] == "Critical"]
    assert len(critical) == 1


def test_dict_key_order_does_not_prevent_duplicate_detection():
    """10. Different key orders in tool inputs normalize to identical JSON strings."""
    trace = {
        "events": [
            {"id": "1", "type": "tool_call", "tool": "query", "input": {"a": 1, "b": 2, "c": 3}},
            {"id": "2", "type": "tool_call", "tool": "query", "input": {"c": 3, "a": 1, "b": 2}},
            {"id": "3", "type": "tool_call", "tool": "query", "input": {"b": 2, "c": 3, "a": 1}},
        ]
    }
    res = analyze_trace(trace)
    repeated = [f for f in res["findings"] if "Repeated" in f["title"]]
    assert len(repeated) == 1
    assert "called 3 times" in repeated[0]["evidence"]


def test_failed_trace_demo():
    """Verify analyzer correctly analyzes the synthetic failed_trace.json example."""
    failed_path = EXAMPLES_DIR / "failed_trace.json"
    with open(failed_path, "r", encoding="utf-8") as f:
        failed_trace = json.load(f)

    res = analyze_trace(failed_trace)
    assert res["event_count"] == 8
    assert res["finding_count"] == 4

    severities = [f["severity"] for f in res["findings"]]
    assert severities == ["Critical", "High", "Medium", "Medium"]

    # Check that individual findings are present
    titles = [f["title"] for f in res["findings"]]
    assert any("Explicit error event" in t for t in titles)
    assert any("Repeated identical tool calls" in t for t in titles)
    assert any("Timeout" in t for t in titles)
    assert any("Unmatched tool call" in t for t in titles)


def test_evidence_bounding():
    """Ensure evidence is bounded and does not exceed max characters."""
    long_error = "x" * 2500
    trace = {
        "events": [
            {"id": "e1", "type": "error", "error": long_error}
        ]
    }
    res = analyze_trace(trace)
    finding = res["findings"][0]
    assert len(finding["evidence"]) <= 1000
    assert finding["evidence"].endswith("...")


def test_duplicate_and_missing_ids():
    """Duplicate event IDs or missing tool_call IDs are flagged as Medium findings."""
    trace = {
        "events": [
            {"id": "dup-1", "type": "tool_call", "tool": "t1"},
            {"id": "dup-1", "type": "tool_call", "tool": "t2"},
            {"type": "tool_call", "tool": "t3"},  # missing id
            {"type": "tool_result", "output": "ok"},  # missing call_id
        ]
    }
    res = analyze_trace(trace)
    mediums = [f for f in res["findings"] if f["severity"] == "Medium"]
    assert any("Duplicate event identifier" in f["title"] for f in mediums)
    assert any("Tool call missing identifier" in f["title"] for f in mediums)
    assert any("Tool result missing call_id" in f["title"] for f in mediums)
