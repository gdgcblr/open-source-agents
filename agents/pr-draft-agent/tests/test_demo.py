"""The demo operates only on disposable synthetic repositories."""

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from examples import create_demo_repo as demo


def git(root: Path, *args: str) -> str:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    return subprocess.check_output(["git", "-C", str(root), *args], env=env, text=True)


def test_demo_ignores_inherited_git_overrides(tmp_path, monkeypatch):
    victim = tmp_path / "victim"
    victim.mkdir()
    subprocess.run(["git", "init", "--quiet", str(victim)], check=True)
    original = (victim / ".git" / "config").read_bytes()
    monkeypatch.setenv("GIT_DIR", str(victim / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(victim))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "external-index"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.worktree")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(victim))
    root = tmp_path / "demo"
    root.mkdir()
    monkeypatch.setattr(demo.tempfile, "mkdtemp", lambda **kwargs: str(root))
    demo.main()
    assert (victim / ".git" / "config").read_bytes() == original
    assert not (tmp_path / "external-index").exists()
    assert git(root, "diff", "--cached", "--name-only").strip() == "config_loader.py"
    assert git(root, "log", "-1", "--format=%ae").strip() == "demo@example.invalid"
    assert (root / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text() == demo.TEMPLATE


def test_demo_disables_global_hooks_and_signing(tmp_path, monkeypatch):
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 99\n")
    hook.chmod(0o755)
    config = tmp_path / "gitconfig"
    config.write_text(f"[core]\n hooksPath = {hooks}\n[commit]\n gpgSign = true\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    root = tmp_path / "demo"
    root.mkdir()
    monkeypatch.setattr(demo.tempfile, "mkdtemp", lambda **kwargs: str(root))
    demo.main()
    assert git(root, "rev-list", "--count", "HEAD").strip() == "1"


@pytest.mark.parametrize("inside_git_checkout", [True, False])
def test_demo_uses_fresh_paths_outside_checkout(tmp_path, monkeypatch, inside_git_checkout):
    source_root = tmp_path / "source"
    project = source_root / "agents" / "pr-draft-agent"
    examples = project / "examples"
    examples.mkdir(parents=True)
    script = examples / "create_demo_repo.py"
    shutil.copyfile(demo.__file__, script)
    if inside_git_checkout:
        (source_root / ".git").mkdir()
    protected_root = source_root if inside_git_checkout else project
    spec = importlib.util.spec_from_file_location("copied_demo", script)
    assert spec is not None and spec.loader is not None
    copied_demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(copied_demo)
    monkeypatch.setattr(copied_demo.tempfile, "gettempdir", lambda: str(protected_root))
    create = demo.tempfile.mkdtemp
    roots = []

    def make_root(**kwargs):
        assert not Path(kwargs["dir"]).is_relative_to(protected_root)
        root = Path(create(prefix=kwargs["prefix"], dir=tmp_path))
        roots.append(root)
        return str(root)

    monkeypatch.setattr(demo.tempfile, "mkdtemp", make_root)
    copied_demo.main()
    before = (roots[0] / "config_loader.py").read_bytes()
    copied_demo.main()
    assert roots[0] != roots[1]
    assert (roots[0] / "config_loader.py").read_bytes() == before
