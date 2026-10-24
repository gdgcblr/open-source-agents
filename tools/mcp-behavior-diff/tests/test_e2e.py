"""End-to-end tests against the bundled toy server (spawns real subprocesses)."""

import json
import sys
from pathlib import Path

import pytest

from mcp_behavior_diff.cli import main

TOY = Path(__file__).resolve().parent.parent / "examples" / "toy_server" / "toy_server.py"


def make_fixture(tmp_path, calls: str, extra_env: str = "", limits: str = "") -> Path:
    toy = tmp_path / "toy_server.py"
    toy.write_text(TOY.read_text())
    server = "command: {py}, args: [toy_server.py, {v}]{env}"
    path = tmp_path / "fixture.yaml"
    path.write_text(
        "version: 1\nservers:\n"
        f"  old: {{{server.format(py=sys.executable, v='v1', env=extra_env)}}}\n"
        f"  new: {{{server.format(py=sys.executable, v='v2', env=extra_env)}}}\n"
        f"calls:\n{calls}\n{limits}"
    )
    return path


def run(path, *flags, capsys):
    code = main(["diff", str(path), "--yes", *flags])
    return code, capsys.readouterr()


def test_detects_behavior_change_invisible_to_schema(tmp_path, capsys):
    fx = make_fixture(
        tmp_path,
        "  - {id: greet, tool: greet, arguments: {name: W}, read_only: true}\n"
        "  - {id: add, tool: add, arguments: {a: 1, b: 2}, read_only: true}",
    )
    code, out = run(fx, capsys=capsys)
    assert code == 1
    assert "[~] greet" in out.out and "[=] add" in out.out


def test_identical_servers_exit_zero(tmp_path, capsys):
    fx = make_fixture(tmp_path, "  - {id: add, tool: add, arguments: {a: 1, b: 2}, read_only: true}")
    code, _ = run(fx, capsys=capsys)
    assert code == 0


def test_destructive_tool_is_never_called(tmp_path, capsys):
    marker = tmp_path / "marker"
    fx = make_fixture(
        tmp_path,
        "  - {id: boom, tool: delete_all, read_only: true}",
        extra_env=f", env: {{TOY_MARKER: '{marker}'}}",
    )
    code, out = run(fx, capsys=capsys)
    assert code == 3  # incomplete: nothing could be executed
    assert "NOT EXECUTED" in out.out
    assert not marker.exists(), "destructive tool was invoked!"


def test_unlisted_tool_is_never_called(tmp_path, capsys):
    fx = make_fixture(tmp_path, "  - {id: ghost, tool: does_not_exist, read_only: true}")
    code, out = run(fx, capsys=capsys)
    assert code == 3 and "NOT EXECUTED" in out.out  # a typo'd tool must never look like "no change"


def test_secrets_in_tool_output_are_redacted_in_report(tmp_path, capsys):
    fx = make_fixture(tmp_path, "  - {id: leak, tool: leak, read_only: true}")
    report = tmp_path / "report.json"
    code, out = run(fx, "--json-out", str(report), capsys=capsys)
    text = report.read_text() + out.out
    assert "ghp_A1b2" not in text and "[REDACTED]" in text


def test_parent_secrets_do_not_reach_server(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "do-not-leak-me-123")
    fx = make_fixture(tmp_path, "  - {id: env, tool: env_names, read_only: true}")
    report = tmp_path / "report.json"
    run(fx, "--json-out", str(report), capsys=capsys)
    assert "SUPER_SECRET_TOKEN" not in report.read_text()


def test_refuses_to_run_non_interactively_without_yes(tmp_path, capsys, monkeypatch):
    fx = make_fixture(tmp_path, "  - {id: add, tool: add, arguments: {a: 1, b: 2}, read_only: true}")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert main(["diff", str(fx)]) == 2
    assert "--yes" in capsys.readouterr().err


def test_report_refuses_overwrite_and_symlink(tmp_path, capsys):
    fx = make_fixture(tmp_path, "  - {id: add, tool: add, arguments: {a: 1, b: 2}, read_only: true}")
    report = tmp_path / "r.json"
    report.write_text("{}")
    code, out = run(fx, "--json-out", str(report), capsys=capsys)
    assert code == 2 and "already exists" in out.err
    link = tmp_path / "link.json"
    link.symlink_to(tmp_path / "elsewhere.json")
    code, out = run(fx, "--json-out", str(link), "--force", capsys=capsys)
    assert code == 2 and "symlink" in out.err


def test_server_that_cannot_start_reports_cleanly(tmp_path, capsys):
    fx = tmp_path / "f.yaml"
    fx.write_text(
        "version: 1\nservers:\n  old: {command: definitely-not-a-real-binary}\n  new: {command: definitely-not-a-real-binary}\n"
        "calls:\n  - {id: a, tool: t, read_only: true}\n"
    )
    code, out = run(fx, capsys=capsys)
    assert code == 2 and "could not start" in out.err


def test_check_command_executes_nothing(tmp_path, capsys):
    fx = make_fixture(tmp_path, "  - {id: add, tool: add, arguments: {a: 1, b: 2}, read_only: true}")
    assert main(["check", str(fx)]) == 0
    assert "nothing was executed" in capsys.readouterr().out


def test_secret_key_in_structured_output_is_redacted(tmp_path, capsys):
    fx = make_fixture(tmp_path, "  - {id: sf, tool: secret_field, read_only: true}")
    report = tmp_path / "report.json"
    run(fx, "--json-out", str(report), capsys=capsys)
    assert "correct-horse-battery" not in report.read_text()


def test_timeout_is_reported_remaining_calls_skipped_and_never_green(tmp_path, capsys):
    fx = make_fixture(
        tmp_path,
        "  - {id: hang, tool: slow, read_only: true}\n  - {id: after, tool: add, arguments: {a: 1, b: 1}, read_only: true}",
        limits="limits: {call_timeout_s: 1}",
    )
    report = tmp_path / "report.json"
    code, _ = run(fx, "--json-out", str(report), capsys=capsys)
    data = json.loads(report.read_text())
    assert [r["status"] for r in data["old"]] == ["timeout", "skipped"]
    assert [r["status"] for r in data["new"]] == ["timeout", "skipped"]
    assert code == 3
