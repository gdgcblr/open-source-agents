import json

from typer.testing import CliRunner

from evals import fixtures as fx
from prcheck.cli import EXIT_NOT_READY, EXIT_READY, EXIT_USAGE, app
from prcheck.models import REPORT_SCHEMA_VERSION

runner = CliRunner()


def test_ready_project_exits_zero(tmp_path):
    project = fx.build_repo(tmp_path)
    result = runner.invoke(app, ["check", str(project), "--no-git"])
    assert result.exit_code == EXIT_READY, result.output
    assert "READY" in result.output


def test_broken_project_exits_one(tmp_path):
    project = fx.build_repo(tmp_path, files={"README.md": None})
    result = runner.invoke(app, ["check", str(project), "--no-git"])
    assert result.exit_code == EXIT_NOT_READY
    assert "D1" in result.output


def test_json_output_is_the_report(tmp_path):
    project = fx.build_repo(tmp_path)
    result = runner.invoke(app, ["check", str(project), "--no-git", "--json"])
    data = json.loads(result.stdout)
    assert data["schema_version"] == REPORT_SCHEMA_VERSION
    assert data["summary"]["ready"] is True
    assert {c["id"] for c in data["checks"]} >= {"S1", "D2", "X2", "G1"}


def test_missing_folder_is_a_usage_error(tmp_path):
    result = runner.invoke(app, ["check", str(tmp_path / "nope")])
    assert result.exit_code == EXIT_USAGE


def test_ai_without_key_is_skipped_not_failed(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr("prcheck.cli._load_dotenv", lambda: [])
    project = fx.build_repo(tmp_path)
    result = runner.invoke(app, ["check", str(project), "--no-git", "--ai", "--json"])
    assert result.exit_code == EXIT_READY
    assert json.loads(result.stdout)["ai"]["status"] == "skipped"


def test_rules_lists_every_check():
    result = runner.invoke(app, ["rules"])
    assert result.exit_code == 0
    for check_id in ("S1", "D4", "M2", "X4", "G3"):
        assert check_id in result.output
