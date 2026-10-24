"""Tests for the CLI orchestration (via --diff-file, no real git)."""

import os

import pytest

from commit_assistant import cli


def _fixture(fixtures_dir, name):
    return os.path.join(fixtures_dir, name)


def test_cli_add_module_feat(fixtures_dir, capsys):
    code = cli.main(["--diff-file", _fixture(fixtures_dir, "add_module.diff"), "--provider", "mock"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert out.startswith("feat(commit_assistant): ")


def test_cli_docs_message(fixtures_dir, capsys):
    code = cli.main(["--diff-file", _fixture(fixtures_dir, "docs_only.diff"), "--provider", "mock"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert out.startswith("docs")


def test_cli_no_body(fixtures_dir, capsys):
    code = cli.main(
        ["--diff-file", _fixture(fixtures_dir, "add_module.diff"), "--provider", "mock", "--no-body"]
    )
    out = capsys.readouterr().out.strip()
    assert code == cli.EXIT_OK
    assert "\n" not in out


def test_cli_missing_diff_file(capsys):
    code = cli.main(["--diff-file", "does_not_exist.diff", "--provider", "mock"])
    err = capsys.readouterr().err
    assert code == cli.EXIT_ERROR
    assert "not found" in err.lower()


def test_cli_empty_diff_file(tmp_path, capsys):
    empty = tmp_path / "empty.diff"
    empty.write_text("", encoding="utf-8")
    code = cli.main(["--diff-file", str(empty), "--provider", "mock"])
    err = capsys.readouterr().err
    assert code == cli.EXIT_NO_CHANGES
    assert "no staged changes" in err.lower()


def test_cli_auto_defaults_to_mock_without_key(fixtures_dir, monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PROVIDER", raising=False)
    code = cli.main(["--diff-file", _fixture(fixtures_dir, "add_module.diff")])
    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert out.startswith("feat")


def test_cli_model_ignored_note_for_mock(fixtures_dir, capsys):
    code = cli.main(
        ["--diff-file", _fixture(fixtures_dir, "add_module.diff"), "--provider", "mock", "--model", "gpt-4o"]
    )
    captured = capsys.readouterr()
    assert code == cli.EXIT_OK
    assert "ignored by the mock provider" in captured.err
