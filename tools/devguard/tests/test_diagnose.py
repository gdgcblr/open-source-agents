"""Tests for build and test failure diagnosis engine."""

import json
from pathlib import Path
import sys
import pytest
from click.testing import CliRunner

from devguard.diagnose import (
    diagnose_failure,
    extract_observed_errors,
    extract_traceback_locations,
    DiagnosticReport,
)
from devguard.runner import CommandResult
from devguard.cli import main


class MockDiagnosisProvider:
    """Mock AI provider returning structured diagnostic JSON."""
    name: str = "gemini"

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.last_prompt = None

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        if self.should_fail:
            raise RuntimeError("Rate limited")
        return json.dumps({
            "observed_errors": ["ImportError: cannot import name 'missing'"],
            "likely_causes": ["Circular import or missing dependency in venv"],
            "suggested_diagnostic_steps": ["Check import path in core.py"],
            "potential_fixes": ["Import module directly or re-install package"],
        })


def test_extract_tracebacks():
    """Extract file:line locations from Python and compiler outputs."""
    output = (
        'Traceback (most recent call last):\n'
        '  File "/workspace/app/main.py", line 42, in <module>\n'
        '    run_app()\n'
        '  File "/workspace/app/core.py", line 105, in run_app\n'
        '    raise ValueError("invalid configuration")\n'
    )
    locations = extract_traceback_locations(output)
    assert "/workspace/app/main.py:42" in locations
    assert "/workspace/app/core.py:105" in locations


def test_extract_observed_errors():
    """Extract recognized exception and error messages."""
    output = (
        "running tests...\n"
        "E   AssertionError: assert 1 == 2\n"
        "FAILED tests/test_core.py::test_calc - AssertionError\n"
        "ValueError: invalid format specified\n"
    )
    errors = extract_observed_errors(output)
    assert any("AssertionError" in e for e in errors)
    assert any("ValueError" in e for e in errors)


def test_deterministic_diagnosis_on_failure():
    """Test deterministic rule-based diagnosis when AI is absent."""
    result = CommandResult(
        exit_code=1,
        stdout="",
        stderr="ModuleNotFoundError: No module named 'nonexistent_package'\n",
    )
    report = diagnose_failure(
        command=["python3", "-m", "pytest"],
        result=result,
        duration_ms=120.0,
        provider=None,
    )
    assert isinstance(report, DiagnosticReport)
    assert report.exit_code == 1
    assert "offline-rule-based" in report.source
    assert any("ModuleNotFoundError" in e for e in report.observed_errors)
    assert any("missing from the environment" in c for c in report.likely_causes)


def test_ai_assisted_diagnosis():
    """Test AI-assisted diagnosis with valid mock response."""
    result = CommandResult(
        exit_code=1,
        stdout="",
        stderr="ImportError: cannot import name 'missing'\n",
    )
    mock_provider = MockDiagnosisProvider()
    report = diagnose_failure(
        command=["python3", "main.py"],
        result=result,
        duration_ms=90.0,
        provider=mock_provider,
    )
    assert report.source == "ai-assisted (gemini)"
    assert "Circular import" in report.likely_causes[0]
    assert "Check import path" in report.suggested_diagnostic_steps[0]


def test_secret_redaction_in_diagnose():
    """Ensure secrets in stderr/stdout are redacted before sending to model."""
    result = CommandResult(
        exit_code=1,
        stdout="connecting with DB=postgres://user:secretpass123@localhost:5432/db\n",
        stderr="API_KEY=AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q failed\n",
    )
    mock_provider = MockDiagnosisProvider()
    diagnose_failure(
        command=["python3", "connect.py"],
        result=result,
        duration_ms=100.0,
        provider=mock_provider,
    )
    assert "secretpass123" not in mock_provider.last_prompt
    assert "AIzaSy" not in mock_provider.last_prompt
    assert "[REDACTED_DB_PASSWORD]" in mock_provider.last_prompt
    assert "[REDACTED" in mock_provider.last_prompt


def test_cli_diagnose_success(runner: CliRunner, sample_config_file: Path):
    """Diagnosing a succeeding command reports clean success and exits 0."""
    res = runner.invoke(
        main,
        ["diagnose", "-c", str(sample_config_file), "--", "echo", "all good"],
    )
    assert res.exit_code == 0
    assert "Command succeeded" in res.output
    assert "No failure to diagnose" in res.output


def test_cli_diagnose_denied_command(runner: CliRunner, sample_config_file: Path):
    """Diagnosing a denied command is refused by policy and never executes."""
    res = runner.invoke(
        main,
        ["diagnose", "-c", str(sample_config_file), "--", "git", "clean", "-fdx"],
    )
    assert res.exit_code == 1
    assert "[DENIED]" in res.output
    assert "Cannot diagnose denied command" in res.output


def test_cli_diagnose_failure_flow(runner: CliRunner, tmp_path: Path):
    """Diagnosing a failing command prints structured report."""
    cfg = tmp_path / "allow_py.yaml"
    cfg.write_text("default_policy: ask\nallow:\n  - ['python3', '-c']\n", encoding="utf-8")

    res = runner.invoke(
        main,
        [
            "diagnose",
            "-c", str(cfg),
            "--fallback",
            "--",
            "python3",
            "-c",
            "import sys; sys.stderr.write('ModuleNotFoundError: No module test\\n'); sys.exit(2)",
        ],
    )
    # Exits with command's exit code
    assert res.exit_code == 2
    assert "DevGuard Failure Diagnosis" in res.output
    assert "[Observed Evidence]" in res.output
    assert "[Likely Causes (Hypotheses)]" in res.output
    assert "[Suggested Diagnostic Steps]" in res.output
