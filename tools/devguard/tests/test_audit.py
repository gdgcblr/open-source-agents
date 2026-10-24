"""Tests for audit history logging, secret redaction, and approval workflows."""

import json
from pathlib import Path
import pytest
from click.testing import CliRunner

from devguard.audit import get_audit_history, record_audit, MAX_HISTORY_LINES
from devguard.redact import redact_secrets
from devguard.cli import main


def test_redact_secrets_patterns():
    """Verify redaction of various credentials and sensitive tokens."""
    # Standalone Bearer token
    assert "Bearer [REDACTED]" in redact_secrets("Token: Bearer secret_token_123456789")

    # Authorization header
    assert "Authorization: [REDACTED]" in redact_secrets("Authorization: Bearer secret_token_123456789")

    # OpenAI key
    assert "[REDACTED_OPENAI_KEY]" in redact_secrets("OPENAI_KEY=sk-abcdefghijklmnopqrstuvwxyz1234")

    # GitHub PAT
    assert "[REDACTED_GITHUB_PAT]" in redact_secrets("ghp_123456789012345678901234567890123456")

    # Database URL
    assert "postgres://admin:[REDACTED_DB_PASSWORD]@localhost:5432/mydb" in redact_secrets(
        "postgres://admin:super_secret_pw@localhost:5432/mydb"
    )

    # Generic key assignment
    assert "api_key=[REDACTED]" in redact_secrets("api_key='secret_api_token_here'")


def test_audit_record_creation_and_retrieval(tmp_path: Path):
    """Test creating an audit record and reading it back."""
    history_file = tmp_path / "test_history.jsonl"
    record = record_audit(
        command=["git", "commit", "-m", "secret_token_123456789"],
        executable="git",
        decision="ASK",
        approval_status="approved",
        matched_rule=("git", "commit"),
        exit_code=0,
        duration_ms=45.2,
        raw_output="committed changes with key=AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q",
        history_path=history_file,
    )

    assert record.decision == "ASK"
    assert record.approval_status == "approved"
    # Output snippet was redacted
    assert "[REDACTED_GEMINI_KEY]" in record.output_snippet

    records = get_audit_history(limit=10, history_path=history_file)
    assert len(records) == 1
    assert records[0]["executable"] == "git"
    assert records[0]["exit_code"] == 0


def test_history_pruning_on_overflow(tmp_path: Path):
    """When history exceeds MAX_HISTORY_LINES, older entries are safely pruned."""
    history_file = tmp_path / "overflow_history.jsonl"
    # Write MAX_HISTORY_LINES + 50 entries
    lines = [json.dumps({"idx": i, "cmd": "test"}) for i in range(MAX_HISTORY_LINES + 50)]
    history_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Adding one more record triggers pruning
    record_audit(
        command=["echo", "done"],
        executable="echo",
        decision="ALLOW",
        approval_status="not_required",
        history_path=history_file,
    )

    updated_lines = history_file.read_text(encoding="utf-8").splitlines()
    assert len(updated_lines) <= (MAX_HISTORY_LINES // 2) + 2


def test_cli_history_command(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test 'devguard history' CLI command."""
    monkeypatch.chdir(tmp_path)
    # Empty history
    res_empty = runner.invoke(main, ["history"])
    assert res_empty.exit_code == 0
    assert "No execution history" in res_empty.output

    # Record two actions
    history_file = tmp_path / ".devguard" / "history.jsonl"
    record_audit(["echo", "1"], "echo", "ALLOW", "not_required", exit_code=0, history_path=history_file)
    record_audit(["git", "commit"], "git", "ASK", "approved", exit_code=0, history_path=history_file)

    # Test table output
    res_table = runner.invoke(main, ["history"])
    assert res_table.exit_code == 0
    assert "DevGuard Execution History" in res_table.output
    assert "ALLOW" in res_table.output
    assert "ASK" in res_table.output

    # Test JSON output
    res_json = runner.invoke(main, ["history", "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.output)
    assert len(data) == 2
    assert data[0]["executable"] == "git"  # newest first


def test_non_interactive_blocked(runner: CliRunner, sample_config_file: Path):
    """Commands requiring confirmation must fail safely in non-interactive mode."""
    res = runner.invoke(
        main,
        ["run", "-c", str(sample_config_file), "--non-interactive", "--", "git", "commit", "-m", "update"],
    )
    assert res.exit_code == 1
    assert "[REFUSED]" in res.output
    assert "environment is non-interactive" in res.output


def test_rejected_command_never_executes(runner: CliRunner, sample_config_file: Path, tmp_path: Path):
    """When user rejects confirmation, the command is not executed."""
    canary = tmp_path / "canary.txt"
    # Command creates canary if executed
    res = runner.invoke(
        main,
        ["run", "-c", str(sample_config_file), "--", "git", "commit", "-m", f"touch {canary}"],
        input="n\n",
    )
    assert res.exit_code == 1
    assert "Execution cancelled by user" in res.output
    assert not canary.exists()
