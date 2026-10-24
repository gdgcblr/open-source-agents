import sys
import os
import pytest

# Add parent directory to python path for tool and agent imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools import LogAnalyzerTool, TestInspectorTool
from agent import TracePilotAgent

def test_log_analyzer_tool():
    sample_log = """
    Traceback (most recent call last):
      File "app/main.py", line 45, in run
        db.connect()
    ValueError: Invalid connection string
    """
    result = LogAnalyzerTool.run(sample_log)
    assert result["total_lines_analyzed"] > 0
    assert len(result["errors_detected"]) == 1
    assert result["errors_detected"][0]["message"] == "Invalid connection string"
    assert len(result["stack_frames"]) == 1
    assert result["stack_frames"][0]["file"] == "app/main.py"
    assert result["stack_frames"][0]["line"] == "45"

def test_test_inspector_tool():
    sample_output = """
    FAILED tests/test_api.py::test_get_user - AssertionError: expected 200 got 500
    === 1 failed, 3 passed in 0.15s ===
    """
    result = TestInspectorTool.run(sample_output)
    assert result["total_failures"] == 1
    assert result["failing_tests"][0]["test_name"] == "tests/test_api.py::test_get_user"
    assert result["test_summary"]["failed"] == 1
    assert result["test_summary"]["passed"] == 3

def test_trace_pilot_agent():
    sample_log = """
    FAILED tests/test_db.py::test_timeout - TimeoutError: Operation timed out
    File "db.py", line 12, in execute
        raise TimeoutError("Operation timed out")
    """
    agent = TracePilotAgent()
    investigation = agent.investigate(sample_log)

    assert "bug_report" in investigation
    assert "log_analysis" in investigation
    assert "test_analysis" in investigation

    report_md = agent.render_markdown_report(investigation)
    assert "TracePilot Investigation Report" in report_md
    assert "Confirmed Facts" in report_md
    assert "Hypotheses" in report_md
    assert "Reproduction Steps" in report_md
