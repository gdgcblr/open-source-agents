"""The shared workspace: one folder per task, and the ADK function tools over it.

Files live in ``<workspace>/<task_id>/`` (``TEAM_WORKSPACE`` or ``./workspace``).
For a bug-fix task that folder is a shallow git clone of the repository. The
task id comes from ADK session state, never from the model, and every path is
re-checked here even though ``before_tool_callback`` checks writes first.

Nothing in a cloned repository is ever executed. The only commands run are
``git clone`` and read-only ``git diff`` / ``git status`` / ``git add -N``.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from google.adk.tools import ToolContext

from shared_memory.guardrails import check_repo_source, check_write

MAX_READ_CHARS = 20_000
MAX_LIST = 400
MAX_DIFF_CHARS = 30_000
GIT_TIMEOUT = 180


def root() -> Path:
    return Path(os.environ.get("TEAM_WORKSPACE") or "workspace")


def task_dir(task_id: str) -> Path:
    if not task_id or "/" in task_id or "\\" in task_id or ".." in task_id:
        raise ValueError(f"bad task id {task_id!r}")
    return root() / task_id


def task_files(task_id: str) -> list[str]:
    base = task_dir(task_id)
    if not base.is_dir():
        return []
    return sorted(
        rel for p in base.rglob("*")
        if p.is_file() and ".git" not in (rel := p.relative_to(base).as_posix()).split("/")
    )


def _manifest(task_id: str) -> Path:
    return root() / f"{task_id}.written.json"


def written_files(task_id: str) -> list[str]:
    """Files the agents themselves wrote for this task (the write cap counts these)."""
    path = _manifest(task_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


def count_files(task_id: str) -> int:
    return len(written_files(task_id)) if task_id else 0


def _resolve(task_id: str, path: str) -> Path:
    base = task_dir(task_id).resolve()
    target = (base / path.replace("\\", "/")).resolve()
    if base != target and base not in target.parents:
        raise ValueError("path escapes the task workspace")
    if ".git" in target.relative_to(base).parts:
        raise ValueError("the .git directory is off limits")
    return target


def _git(task_id: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(task_dir(task_id)), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=GIT_TIMEOUT, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def is_repo(task_id: str) -> bool:
    return (task_dir(task_id) / ".git").is_dir()


# -- set-up and results (called by the CLI, not by models) --------------------


def clone_repo(source: str, task_id: str) -> None:
    """Shallow-clone an https:// URL or a local directory into the task folder."""
    reason = check_repo_source(source)
    if reason:
        raise ValueError(reason)
    dest = task_dir(task_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if Path(source).is_dir():
        source = Path(source).resolve().as_uri()  # file:// so --depth applies
    done = subprocess.run(
        ["git", "clone", "--depth", "1", "--", source, str(dest)],
        capture_output=True, text=True, timeout=GIT_TIMEOUT,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if done.returncode != 0:
        raise RuntimeError(f"git clone failed: {done.stderr.strip()[:300]}")


def diff_text(task_id: str) -> str:
    """Every change against the cloned commit, new files included."""
    if not is_repo(task_id):
        return ""
    _git(task_id, "add", "--intent-to-add", "--all")
    return _git(task_id, "diff", "--no-color", "--no-ext-diff").stdout


def export_patch(task_id: str) -> Path | None:
    text = diff_text(task_id)
    if not text.strip():
        return None
    path = root() / f"{task_id}.patch"
    path.write_text(text, encoding="utf-8")
    return path


# -- ADK function tools --------------------------------------------------------


def list_files(tool_context: ToolContext, directory: str = "") -> dict:
    """List files in this task's workspace (the cloned repository for a bug fix).

    Args:
        directory: Optional relative folder to list, for example "src". Empty lists everything.
    """
    task_id = tool_context.state.get("task_id", "")
    prefix = directory.strip().strip("/").replace("\\", "/")
    files = [f for f in task_files(task_id) if not prefix or f.startswith(prefix + "/")]
    return {"files": files[:MAX_LIST], "total": len(files), "truncated": len(files) > MAX_LIST}


def read_file(path: str, tool_context: ToolContext) -> dict:
    """Read one file from this task's workspace.

    Args:
        path: Relative path of the file, as returned by list_files.
    """
    task_id = tool_context.state.get("task_id", "")
    try:
        target = _resolve(task_id, path)
    except ValueError as exc:
        return {"status": "error", "reason": str(exc)}
    if not target.is_file():
        return {"status": "error", "reason": f"{path} does not exist"}
    text = target.read_text(encoding="utf-8", errors="replace")
    return {"status": "ok", "path": path, "content": text[:MAX_READ_CHARS],
            "truncated": len(text) > MAX_READ_CHARS}


def write_file(path: str, content: str, tool_context: ToolContext) -> dict:
    """Create or overwrite one file in this task's workspace.

    Args:
        path: Short relative path, for example "src/parser.py".
        content: The complete new file content.
    """
    task_id = tool_context.state.get("task_id", "")
    already = written_files(task_id)
    reason = check_write(path, content, len(already) - (path in already))
    if reason:
        return {"status": "denied", "reason": reason}
    try:
        target = _resolve(task_id, path)
    except ValueError as exc:
        return {"status": "denied", "reason": str(exc)}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    if path not in already:
        _manifest(task_id).write_text(json.dumps(already + [path]), encoding="utf-8")
    return {"status": "ok", "path": path, "bytes": len(content.encode("utf-8"))}


def show_diff(tool_context: ToolContext) -> dict:
    """Show the git diff of everything changed in the cloned repository so far."""
    task_id = tool_context.state.get("task_id", "")
    if not is_repo(task_id):
        return {"status": "error", "reason": "this task has no cloned repository"}
    text = diff_text(task_id)
    return {"status": "ok", "diff": text[:MAX_DIFF_CHARS] or "(no changes)",
            "truncated": len(text) > MAX_DIFF_CHARS}
