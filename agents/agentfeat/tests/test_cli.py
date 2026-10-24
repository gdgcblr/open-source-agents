"""CLI integration tests in isolated environments."""

from pathlib import Path
import pytest

from agentfeat.cli import main


def test_cli_scan_command(tmp_path: Path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    result = main(["scan", "--target-dir", str(tmp_path)])
    assert result == 0


def test_cli_plan_command(tmp_path: Path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    result = main(["plan", "Add OAuth login", "--target-dir", str(tmp_path)])
    assert result == 0


def test_cli_run_dry_run_never_modifies_files(tmp_path: Path):
    app_file = tmp_path / "app.py"
    app_file.write_text("INITIAL_STATE = True\n", encoding="utf-8")

    # Run in offline dry-run mode
    result = main(["run", "Add new feature", "--target-dir", str(tmp_path), "--offline", "--dry-run"])
    assert result == 0

    # Ensure app_file was untouched
    assert app_file.read_text() == "INITIAL_STATE = True\n"
    # Ensure no new files created
    assert not (tmp_path / "feature_core.py").exists()
    assert not (tmp_path / ".agentfeat_backup").exists()


def test_cli_run_apply_creates_backup_and_files(tmp_path: Path):
    app_file = tmp_path / "requirements.txt"
    app_file.write_text("pytest\n", encoding="utf-8")
    pr_output_file = tmp_path / "PR_SUMMARY.md"

    # Run in offline mode with --apply and --save-pr
    result = main([
        "run", "Add feature",
        "--target-dir", str(tmp_path),
        "--offline",
        "--apply",
        "--save-pr", str(pr_output_file),
    ])
    assert result == 0

    # Ensure new files created
    assert (tmp_path / "feature_core.py").exists()
    assert (tmp_path / "tests" / "test_feature.py").exists()

    # Ensure backup created
    assert (tmp_path / ".agentfeat_backup").exists()

    # Ensure PR summary markdown file was written
    assert pr_output_file.exists()
    assert "# Feature:" in pr_output_file.read_text()


def test_cli_dry_run_precedence_over_apply(tmp_path: Path):
    app_file = tmp_path / "app.py"
    app_file.write_text("ORIGINAL = 1\n", encoding="utf-8")

    # Pass both --dry-run and --apply; dry-run must take precedence
    result = main([
        "run", "Add feature",
        "--target-dir", str(tmp_path),
        "--offline",
        "--dry-run",
        "--apply",
    ])
    assert result == 0

    # Workspace must NOT be modified
    assert app_file.read_text() == "ORIGINAL = 1\n"
    assert not (tmp_path / "feature_core.py").exists()


def test_cli_web_subcommand_parser():
    from agentfeat.cli import parse_args
    args = parse_args(["web", "--port", "9000"])
    assert args.command == "web"
    assert args.port == 9000
