import shutil
import subprocess

import pytest

from checker.rules import check_scope

from pathlib import Path
from checker.rules import check_name, check_required_files
from checker.secrets import check_secrets

def test_bad_name(tmp_path):
    d = tmp_path / "tools" / "My_Tool"
    d.mkdir(parents=True)
    assert not check_name(d).passed

def test_generic_name(tmp_path):
    d = tmp_path / "tools" / "demo"
    d.mkdir(parents=True)
    assert not check_name(d).passed

def test_missing_files(tmp_path):
    d = tmp_path / "tools" / "good-name"
    d.mkdir(parents=True)
    assert not check_required_files(d).passed

def test_secret_detected(tmp_path):
    d = tmp_path / "tools" / "good-name"
    d.mkdir(parents=True)
    (d / "app.py").write_text('KEY = "AIza' + "A" * 35 + '"')
    result = check_secrets(d)
    assert not result.passed
    assert "AIza" + "A" * 35 not in result.message   # never leak the value


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def commit_all(root, message):
    git(root, "add", "-A")
    git(root, "commit", "-m", message)


@pytest.fixture
def repo(tmp_path):
    """A temp repo with a 'main' branch, plus a feature branch and an empty project folder."""
    git(tmp_path, "init")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test User")
    git(tmp_path, "config", "commit.gpgsign", "false")
    git(tmp_path, "checkout", "-b", "main")

    (tmp_path / "README.md").write_text("root readme")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "README.md").write_text("tools index")
    commit_all(tmp_path, "base commit")

    git(tmp_path, "checkout", "-b", "feat/my-tool")
    project = tmp_path / "tools" / "my-tool"
    project.mkdir()
    return tmp_path, project


@needs_git
def test_scope_passes_when_only_project_changed(repo):
    root, project = repo
    (project / "main.py").write_text("print('hello')")
    commit_all(root, "add my-tool")

    result = check_scope(project, base="main")
    assert result.passed


@needs_git
def test_scope_allows_index_readme_change(repo):
    root, project = repo
    (project / "main.py").write_text("print('hello')")
    (root / "tools" / "README.md").write_text("tools index with my row")
    commit_all(root, "add my-tool and index row")

    result = check_scope(project, base="main")
    assert result.passed


@needs_git
def test_scope_fails_when_root_file_changed(repo):
    root, project = repo
    (project / "main.py").write_text("print('hello')")
    (root / "notes.txt").write_text("accidental change")
    commit_all(root, "add my-tool and stray file")

    result = check_scope(project, base="main")
    assert not result.passed
    assert "notes.txt" in result.message


@needs_git
def test_scope_fails_when_other_project_touched(repo):
    root, project = repo
    other = root / "tools" / "other-tool"
    other.mkdir()
    (other / "app.py").write_text("someone else's code")
    (project / "main.py").write_text("print('hello')")
    commit_all(root, "touch another contributor's folder")

    result = check_scope(project, base="main")
    assert not result.passed
    assert "other-tool" in result.message


def test_scope_skips_without_git_history(tmp_path):
    project = tmp_path / "tools" / "my-tool"
    project.mkdir(parents=True)

    result = check_scope(project)  # default base "upstream/main" doesn't exist here
    assert result.passed
    assert "Skipped" in result.message