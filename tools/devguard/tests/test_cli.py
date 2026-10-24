"""Integration tests for DevGuard CLI commands using Click CliRunner."""

import pytest
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import patch

from devguard.cli import main


@pytest.fixture
def runner():
    return CliRunner()


def test_cli_version(runner: CliRunner):
    """Test --version flag."""
    res = runner.invoke(main, ["--version"])
    assert res.exit_code == 0
    assert "0.1.0" in res.output


def test_cli_init_creates_config(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test 'devguard init' creates a valid configuration file."""
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(main, ["init"])
    assert res.exit_code == 0
    assert "Initialized DevGuard configuration" in res.output
    assert Path("devguard.yaml").exists()

    # Running again without --force should warn
    res2 = runner.invoke(main, ["init"])
    assert res2.exit_code == 0
    assert "already exists" in res2.output

    # Running with --force should succeed
    res3 = runner.invoke(main, ["init", "--force"])
    assert res3.exit_code == 0
    assert "Initialized DevGuard configuration" in res3.output


def test_cli_run_no_args(runner: CliRunner):
    """Running devguard run without command args should exit 1."""
    res = runner.invoke(main, ["run"])
    assert res.exit_code == 1
    assert "No command specified" in res.output


def test_cli_run_missing_config(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Running devguard run with a missing config should report an error."""
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(main, ["run", "-c", "missing.yaml", "--", "echo", "hi"])
    assert res.exit_code == 1
    assert "Configuration error" in res.output


def test_cli_run_allowed_command(runner: CliRunner, sample_config_file: Path):
    """Running an allowed command executes and exits 0."""
    res = runner.invoke(main, ["run", "-c", str(sample_config_file), "--", "echo", "hello-world"])
    assert res.exit_code == 0
    assert "[ALLOWED]" in res.output
    assert "hello-world" in res.output


def test_cli_run_denied_command(runner: CliRunner, sample_config_file: Path):
    """Running a denied command refuses execution and exits 1."""
    res = runner.invoke(main, ["run", "-c", str(sample_config_file), "--", "git", "clean", "-fdx"])
    assert res.exit_code == 1
    assert "[DENIED]" in res.output
    assert "Explicitly denied by rule" in res.output


def test_cli_run_ask_command_declined(runner: CliRunner, sample_config_file: Path):
    """When a command requires confirmation and user enters 'n', execution is cancelled."""
    res = runner.invoke(
        main,
        ["run", "-c", str(sample_config_file), "--", "git", "commit", "-m", "msg"],
        input="n\n",
    )
    assert res.exit_code == 1
    assert "[CONFIRMATION REQUIRED]" in res.output
    assert "Execution cancelled by user" in res.output


def test_cli_commit_message_empty_diff(runner: CliRunner):
    """commit-message when no diff is staged exits 0 with hint."""
    with patch("devguard.cli.get_staged_diff", return_value=""):
        res = runner.invoke(main, ["commit-message"])
        assert res.exit_code == 0
        assert "No staged changes found" in res.output


def test_cli_commit_message_fallback(runner: CliRunner):
    """commit-message --fallback outputs deterministic conventional message."""
    mock_diff = "diff --git a/test.py b/test.py\n+dummy"
    with patch("devguard.cli.get_staged_diff", return_value=mock_diff), \
         patch("devguard.cli.get_staged_stats", return_value=["tests/test_cli.py"]):
        res = runner.invoke(main, ["commit-message", "--fallback"])
        assert res.exit_code == 0
        assert "Proposed Commit Message" in res.output
        assert "test: update test suite" in res.output
