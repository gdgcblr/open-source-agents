"""Integration and End-to-End tests for AutonomousCodeHealer."""

import os
import sys
import tempfile
import pytest
from healer.core import AutonomousCodeHealer
from healer.reporter import generate_healing_html_dashboard
from healer.ast_guard import validate_code_safety


def test_end_to_end_mock_healing():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_file = os.path.join(tmpdir, "broken_math.py")
        test_file = os.path.join(tmpdir, "test_math.py")

        with open(target_file, "w", encoding="utf-8") as f:
            f.write(
                "def divide(a, b):\n"
                "    return a / b\n\n"
                "def add(a, b):\n"
                "    return a + b + 1\n"
            )

        with open(test_file, "w", encoding="utf-8") as f:
            f.write(
                "import pytest\n"
                "from broken_math import divide, add\n\n"
                "def test_calc():\n"
                "    assert add(2, 3) == 5\n"
                "    assert divide(10, 2) == 5.0\n"
                "    with pytest.raises(ValueError):\n"
                "        divide(5, 0)\n"
            )

        test_cmd = f'"{sys.executable}" -m pytest test_math.py'
        healer = AutonomousCodeHealer(max_attempts=3, mock_mode=True)
        result = healer.heal(target_file, test_cmd)

        assert result["status"] == "healed_successfully"
        assert len(result["diff"]) > 0
        assert result["metrics"]["attempts_made"] >= 1

        # Check healed file content
        with open(target_file, "r", encoding="utf-8") as f:
            healed_content = f.read()
        assert "Cannot divide by zero" in healed_content
        assert "return a + b" in healed_content


def test_already_passing_code():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_file = os.path.join(tmpdir, "good_code.py")
        test_file = os.path.join(tmpdir, "test_good.py")

        with open(target_file, "w", encoding="utf-8") as f:
            f.write("def multiply(a, b):\n    return a * b\n")

        with open(test_file, "w", encoding="utf-8") as f:
            f.write("from good_code import multiply\ndef test_mult():\n    assert multiply(3, 4) == 12\n")

        test_cmd = f'"{sys.executable}" -m pytest test_good.py'
        healer = AutonomousCodeHealer(max_attempts=2, mock_mode=True)
        result = healer.heal(target_file, test_cmd)

        assert result["status"] == "already_passing"
        assert result["metrics"]["attempts_made"] == 0
        assert result["diff"] == ""


def test_rollback_on_failed_attempts():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_file = os.path.join(tmpdir, "unfixable.py")
        test_file = os.path.join(tmpdir, "test_unfixable.py")

        original_text = "def unfixable():\n    return 'original'\n"
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(original_text)

        # Test demands impossible condition
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("def test_impossible():\n    assert 1 == 2\n")

        test_cmd = f'"{sys.executable}" -m pytest test_unfixable.py'
        healer = AutonomousCodeHealer(max_attempts=2, auto_rollback=True, mock_mode=True)
        result = healer.heal(target_file, test_cmd)

        assert result["status"] == "rollback_after_failed_attempts"
        with open(target_file, "r", encoding="utf-8") as f:
            restored_text = f.read()
        assert restored_text == original_text


def test_html_dashboard_generation():
    with tempfile.TemporaryDirectory() as tmpdir:
        report_file = os.path.join(tmpdir, "dashboard.html")
        mock_result = {
            "status": "healed_successfully",
            "file_path": "broken_math.py",
            "original_code": "def add(a, b): return a + b + 1",
            "healed_code": "def add(a, b): return a + b",
            "diff": "- return a + b + 1\n+ return a + b",
            "attempts": [
                {
                    "attempt_num": 1,
                    "ast_safe": True,
                    "ast_reason": "Passed AST check",
                    "test_passed": True,
                    "exit_code": 0,
                    "duration_seconds": 0.42,
                    "error_snippet": ""
                }
            ],
            "metrics": {
                "run_id": "test-run-123",
                "target_file": "broken_math.py",
                "test_command": "pytest test_math.py",
                "duration_seconds": 1.25,
                "attempts_made": 1,
                "diff_lines_changed": 2,
                "mock_mode": True
            }
        }

        html_out = generate_healing_html_dashboard(mock_result, report_file)
        assert os.path.exists(report_file)
        assert "<!DOCTYPE html>" in html_out
        assert "HEALED &amp; VERIFIED" in html_out or "HEALED & VERIFIED" in html_out
        assert "test-run-123" in html_out
        assert "Surgical Code Patch" in html_out


def test_html_dashboard_xss_escaping():
    with tempfile.TemporaryDirectory() as tmpdir:
        report_file = os.path.join(tmpdir, "xss_test.html")
        xss_result = {
            "status": "healed_successfully",
            "file_path": "<script>alert(1)</script>",
            "original_code": "<img src=x onerror=alert('xss')>",
            "healed_code": "def safe(): pass",
            "diff": "+ safe",
            "attempts": [],
            "metrics": {
                "run_id": "xss-test",
                "target_file": "<script>alert(1)</script>",
                "test_command": "pytest",
                "duration_seconds": 0.1,
                "attempts_made": 0,
                "diff_lines_changed": 1,
                "mock_mode": True
            }
        }
        html_out = generate_healing_html_dashboard(xss_result, report_file)
        # Check that dangerous unescaped tags are not injected as raw HTML in the body
        assert "<script>alert(1)</script>" not in html_out.split('<script id="healer-data-payload"')[0]
