"""Clone a repository and fix a bug, offline: a local git repo stands in for GitHub."""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from main import main
from shared_memory.guardrails import check_repo_source
from shared_memory.workspace import (
    clone_repo,
    diff_text,
    list_files,
    read_file,
    show_diff,
    task_files,
    write_file,
)

from conftest import tool_context

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is required")


@pytest.fixture()
def bug_repo(tmp_path):
    repo = tmp_path / "calc-repo"
    repo.mkdir()
    (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(git[:3] + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "add with a bug"], check=True)
    return repo


@pytest.fixture(autouse=True)
def in_tmp(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("source", [
    "ssh://git@github.com/o/r.git", "git@github.com:o/r.git", "ext::sh -c touch% /tmp/x",
    "file:///etc", "--upload-pack=evil", "http://github.com/o/r", "",
])
def test_unsafe_sources_are_refused(source):
    assert check_repo_source(source)


def test_https_and_local_directories_are_allowed(bug_repo):
    assert check_repo_source("https://github.com/owner/repo.git") is None
    assert check_repo_source(str(bug_repo)) is None


def test_clone_tools_and_diff(bug_repo):
    clone_repo(str(bug_repo), "task-fix")
    ctx = tool_context("task-fix")
    assert task_files("task-fix") == ["calc.py"]          # .git is hidden
    assert list_files(ctx)["files"] == ["calc.py"]
    assert read_file(".git/config", ctx)["status"] == "error"
    assert write_file(".git/hooks/post-checkout.sh", "x", ctx)["status"] == "denied"
    assert show_diff(ctx)["diff"] == "(no changes)"

    write_file("calc.py", "def add(a, b):\n    return a + b\n", ctx)
    write_file("test_calc.py", "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n", ctx)
    diff = diff_text("task-fix")
    assert "-    return a - b" in diff and "+    return a + b" in diff
    assert "test_calc.py" in diff                        # new files appear too


def test_fix_command_end_to_end_offline(bug_repo, capsys):
    assert main(["fix", str(bug_repo), "add() subtracts instead of adding", "--mock"]) == 0
    out = capsys.readouterr().out
    task_id = re.search(r"(task-\w+): Fix this bug", out).group(1)
    assert "cloned into" in out
    assert "completed  (5/5 steps)" in out
    assert "raw conversation transfers  0" in out
    assert f"{task_id}.patch" in out
    assert main(["diff", task_id]) == 0
    assert "FIX_NOTES.md" in capsys.readouterr().out
    assert main(["memory", task_id]) == 0
    memory = capsys.readouterr().out
    assert "Offline mock: the bug is not actually fixed" in memory


def test_ask_understands_clone_and_fix(bug_repo, capsys):
    assert main(["ask", f'clone "{bug_repo}" and fix: add subtracts', "--mock"]) == 0
    out = capsys.readouterr().out
    assert "Fix this bug in the repository cloned from" in out
    assert "completed  (5/5 steps)" in out


def test_an_unsafe_repo_is_refused_before_any_task(capsys):
    assert main(["fix", "ssh://git@github.com/o/r.git", "bug", "--mock"]) == 2
    assert "only https://" in capsys.readouterr().err
    assert main(["tasks"]) == 0
    assert "No tasks yet" in capsys.readouterr().out
