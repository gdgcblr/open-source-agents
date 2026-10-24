"""Turning a CLI/UI target (local folder or GitHub URL) into a folder on disk."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

GITHUB_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?"
    r"(?:/(?:tree|blob)/(?P<rest>.+?))?/?$"
)


class SourceError(RuntimeError):
    pass


def _git(*args: str, timeout: int = 180) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(["git", *args], capture_output=True, text=True, timeout=timeout, env=env)


def _split_ref(url: str, rest: str) -> tuple[Optional[str], str]:
    """A tree URL like feat/x/agents/foo is ambiguous, so ask the remote which prefix is a ref."""
    parts = rest.split("/")
    for i in range(1, len(parts) + 1):
        ref = "/".join(parts[:i])
        probe = _git("ls-remote", "--heads", "--tags", url, ref, timeout=60)
        if probe.returncode == 0 and probe.stdout.strip():
            return ref, "/".join(parts[i:])
    # probably a commit sha or the remote is unreachable, let clone report it
    return parts[0], "/".join(parts[1:])


def resolve_target(target: str, subdir: Optional[str], workdir: Path) -> tuple[Path, str]:
    """Return (project folder, label for the report). Remote repos are cloned into workdir."""
    target = target.strip()
    local = Path(target).expanduser()
    if local.exists():
        if not local.is_dir():
            raise SourceError(f"{target} is a file, point FirstRun at the project folder")
        project = local.resolve()
        label = str(project)
    else:
        m = GITHUB_RE.match(target)
        if not m and not target.endswith(".git"):
            raise SourceError(f"{target} is neither a folder nor a GitHub URL")
        if shutil.which("git") is None:
            raise SourceError("git is needed to fetch remote repositories")
        if m:
            url = f"https://github.com/{m['owner']}/{m['repo']}.git"
            ref, path_in_repo = _split_ref(url, m["rest"]) if m["rest"] else (None, "")
        else:
            url, ref, path_in_repo = target, None, ""
        dest = workdir / "source"
        cmd = ["clone", "--depth", "1", "--quiet"]
        if ref:
            cmd += ["--branch", ref]
        result = _git(*cmd, url, str(dest))
        if result.returncode != 0:
            raise SourceError(f"git clone failed: {result.stderr.strip()[-400:]}")
        project = dest / path_in_repo if path_in_repo else dest
        label = target
    if subdir:
        project = project / subdir.strip("/")
        label = f"{label} ({subdir.strip('/')})"
    if not project.is_dir():
        raise SourceError(f"{project} does not exist")
    return project, label
