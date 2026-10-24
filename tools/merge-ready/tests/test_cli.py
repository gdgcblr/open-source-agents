"""Tests for MergeReady command-line interface, formatting, and exit codes."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from merge_ready.cli import main

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_cli_help(capsys):
    """Verify --help exits cleanly and displays usage."""
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "merge-ready" in captured.out
    assert "check" in captured.out


def test_cli_version(capsys):
    """Verify --version displays version."""
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "merge-ready 0.1.0" in captured.out


def test_cli_good_tool_terminal(capsys):
    """Verify clean fixture exits 0 with terminal output."""
    good_dir = str(FIXTURES_DIR / "good-tool")
    code = main(["check", good_dir])
    assert code == 0
    captured = capsys.readouterr()
    assert "MergeReady Contribution Validator" in captured.out
    assert "PASSED" in captured.out
    assert "0 fail" in captured.out


def test_cli_good_tool_json(capsys):
    """Verify JSON format outputs strictly valid parseable JSON."""
    good_dir = str(FIXTURES_DIR / "good-tool")
    code = main(["check", good_dir, "--format", "json"])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["slug"] == "good-tool"
    assert data["summary"]["fail"] == 0
    assert "results" in data


def test_cli_good_tool_markdown(capsys):
    """Verify Markdown format produces GitHub-compatible report."""
    good_dir = str(FIXTURES_DIR / "good-tool")
    code = main(["check", good_dir, "--format", "markdown"])
    assert code == 0
    captured = capsys.readouterr()
    assert "# MergeReady Validation Report" in captured.out
    assert "### Verdict:" in captured.out


def test_cli_bad_agent_exit_code(defective_agent_dir: Path, capsys):
    """Verify defective fixture returns exit code 1."""
    code = main(["check", str(defective_agent_dir)])
    assert code == 1
    captured = capsys.readouterr()
    assert "FAILED" in captured.out


def test_cli_strict_mode(defective_agent_dir: Path):
    """Verify --strict fails when warnings exist."""
    code = main(["check", str(defective_agent_dir), "--strict"])
    assert code == 1


def test_cli_output_file(tmp_path: Path):
    """Verify --output writes report to destination file."""
    good_dir = str(FIXTURES_DIR / "good-tool")
    out_file = tmp_path / "report.json"
    code = main(["check", good_dir, "--format", "json", "--output", str(out_file)])
    assert code == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["summary"]["fail"] == 0


def test_cli_invalid_path():
    """Verify non-existent project directory returns exit code 2."""
    code = main(["check", "non_existent_folder_xyz_123"])
    assert code == 2


def test_cli_json_serialization_failure(monkeypatch, capsys):
    """Verify that report formatting / serialization failure returns exit code 2."""
    def fail_json(report):
        raise TypeError("Simulated JSON serialization crash")

    monkeypatch.setattr("merge_ready.cli.format_json", fail_json)
    code = main(["check", str(FIXTURES_DIR / "good-tool"), "--format", "json"])
    assert code == 2
    captured = capsys.readouterr()
    assert "Operational error" in captured.err


def test_cli_output_file_write_failure(capsys, tmp_path: Path):
    """Verify that failing to write output file returns exit code 2."""
    # Passing a directory path as the output file path causes write_text to fail
    code = main(["check", str(FIXTURES_DIR / "good-tool"), "--output", str(tmp_path)])
    assert code == 2
    captured = capsys.readouterr()
    assert "Error writing report" in captured.err


def test_cli_unexpected_top_level_exception(monkeypatch, capsys):
    """Verify that an unexpected top-level CLI crash returns exit code 2 without uncaught tracebacks."""
    def crash_parser():
        raise RuntimeError("Fatal argument parsing disaster")

    monkeypatch.setattr("merge_ready.cli.build_parser", crash_parser)
    code = main(["check", "test"])
    assert code == 2
    captured = capsys.readouterr()
    assert "Unexpected CLI error" in captured.err


def test_cli_error_verdict_exit_code_2(monkeypatch, capsys):
    """Verify that check execution errors trigger Result: ERROR and exit code 2."""
    from merge_ready.checks import CHECK_REGISTRY

    def crash_l01(ctx, config):
        raise RuntimeError("Simulated crash in layout rule")

    new_registry = [(r, crash_l01 if r == "L01" else fn) for r, fn in CHECK_REGISTRY]
    monkeypatch.setattr("merge_ready.checks.CHECK_REGISTRY", new_registry)

    code = main(["check", str(FIXTURES_DIR / "good-tool")])
    assert code == 2
    captured = capsys.readouterr()
    assert "Result: ERROR" in captured.out

