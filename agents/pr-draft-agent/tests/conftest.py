"""Isolated temporary Git repositories for repository capture tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

_CLEARED_GIT_VARIABLES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_EXTERNAL_DIFF",
)


def _clean_git_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in _CLEARED_GIT_VARIABLES
    }
    environment.update(
        {
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "cat",
            "PAGER": "cat",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
        }
    )
    return environment


@pytest.fixture
def git_env() -> dict[str, str]:
    """A Git environment with redirecting overrides removed."""
    return _clean_git_environment()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fresh repository with local-only identity and configuration."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    path = tmp_path / "repo"
    path.mkdir()
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    excludes = tmp_path / "excludes"
    excludes.write_text("", encoding="utf-8")
    attributes = tmp_path / "attributes"
    attributes.write_text("", encoding="utf-8")
    commit_template = tmp_path / "commit-template"
    commit_template.write_text("", encoding="utf-8")

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=path,
            check=True,
            capture_output=True,
            text=True,
            env=_clean_git_environment(),
        )

    run("init", "-q", "-b", "main")
    run("config", "user.name", "Repository Test")
    run("config", "user.email", "repository-test@example.invalid")
    run("config", "commit.gpgsign", "false")
    run("config", "core.autocrlf", "false")
    run("config", "core.safecrlf", "false")
    run("config", "core.hooksPath", str(hooks))
    run("config", "core.excludesFile", str(excludes))
    run("config", "core.attributesFile", str(attributes))
    run("config", "commit.template", str(commit_template))
    return path


@pytest.fixture
def git(repo: Path):
    """Run Git inside the fixture repository (or an explicit working tree)."""

    def run(
        *args: str,
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd or repo,
            check=check,
            capture_output=True,
            text=True,
            env=_clean_git_environment(),
        )

    return run


@pytest.fixture
def stage(repo: Path, git):
    """Write a file and stage it inside the fixture repository."""

    def add(name: str, content: str | bytes = "staged\n") -> Path:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8", newline="")
        git("add", "--", name)
        return path

    return add
