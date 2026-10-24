"""Git plumbing: staged files, changed line ranges, full tree, HEAD contents."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
MAX_FILE_BYTES = 1_000_000


def _git(repo: Path, *args: str) -> str:
    res = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                         check=False)
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout


def repo_root(start: Path) -> Path:
    return Path(_git(start, "rev-parse", "--show-toplevel").strip())


def staged_files(repo: Path) -> list[str]:
    out = _git(repo, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    return [p for p in out.split("\0") if p]


def tracked_files(repo: Path) -> list[str]:
    return [p for p in _git(repo, "ls-files", "-z").split("\0") if p]


def staged_content(repo: Path, path: str) -> str | None:
    try:
        data = _git(repo, "show", f":{path}")
    except RuntimeError:
        return None
    return data if len(data) <= MAX_FILE_BYTES else None


def head_content(repo: Path, path: str) -> str | None:
    try:
        return _git(repo, "show", f"HEAD:{path}")
    except RuntimeError:
        return None


def working_content(repo: Path, path: str) -> str | None:
    p = repo / path
    try:
        if p.stat().st_size > MAX_FILE_BYTES:
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def staged_changed_lines(repo: Path) -> dict[str, set[int]]:
    """{path: added/modified line numbers in the staged version}."""
    out = _git(repo, "diff", "--cached", "-U0", "--no-color", "--diff-filter=ACMR")
    changed: dict[str, set[int]] = {}
    current: str | None = None
    for line in out.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
        elif current and (m := HUNK_RE.match(line)):
            start, count = int(m.group(1)), int(m.group(2) or "1")
            changed.setdefault(current, set()).update(range(start, start + count))
    return changed


def tracked_under(repo: Path, prefix: str) -> list[str]:
    try:
        out = _git(repo, "ls-files", "-z", "--", prefix)
    except RuntimeError:
        return []
    return [p for p in out.split("\0") if p]


def head_sha(repo: Path) -> str:
    try:
        return _git(repo, "rev-parse", "--short", "HEAD").strip()
    except RuntimeError:
        return "no-head"


def hooks_dir(repo: Path) -> Path:
    path = Path(_git(repo, "rev-parse", "--git-path", "hooks").strip())
    return path if path.is_absolute() else repo / path
