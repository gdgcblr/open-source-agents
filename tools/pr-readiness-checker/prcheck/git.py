"""Thin, read-only wrappers around the git CLI. prcheck never writes to a repository."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

GIT_TIMEOUT_SECONDS = 20


class GitError(RuntimeError):
    pass


def available() -> bool:
    return shutil.which("git") is not None


def run(cwd: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-c", "core.quotepath=off", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(str(exc)) from exc
    if completed.returncode != 0:
        raise GitError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout


def toplevel(path: Path) -> Path | None:
    if not available():
        return None
    try:
        return Path(run(path, "rev-parse", "--show-toplevel").strip()).resolve()
    except GitError:
        return None


def ref_exists(repo: Path, ref: str) -> bool:
    try:
        run(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        return True
    except GitError:
        return False


def merge_base(repo: Path, base: str) -> str:
    return run(repo, "merge-base", base, "HEAD").strip()


def _split_nul(output: str) -> list[str]:
    return [item for item in output.split("\0") if item]


def files_to_commit(path: Path) -> list[str]:
    """Tracked plus untracked-but-not-ignored files under `path`, relative to it."""
    output = run(path, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", ".")
    return sorted({item for item in _split_nul(output) if (path / item).exists()})


def changed_files(repo: Path, since: str) -> list[str]:
    """Files that differ from commit `since`, including uncommitted and untracked files."""
    diffed = _split_nul(run(repo, "diff", "--name-only", "-z", since))
    untracked = _split_nul(run(repo, "ls-files", "-z", "--others", "--exclude-standard"))
    return sorted(set(diffed) | set(untracked))


def numstat(repo: Path, since: str, file: str) -> tuple[int, int]:
    """(lines added, lines removed) for one file since commit `since`."""
    output = run(repo, "diff", "--numstat", since, "--", file).strip()
    if not output:
        return 0, 0
    added, removed, _ = output.split("\t", 2)
    if added == "-":  # binary
        return 0, 0
    return int(added), int(removed)


def path_exists_at(repo: Path, ref: str, path: str) -> bool:
    output = run(repo, "ls-tree", "--name-only", ref, "--", path)
    return bool(output.strip())
