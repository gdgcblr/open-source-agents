"""ADK function tools. The sandbox path comes from tool_context.state, never from the model."""
import os
import re
import shlex
import sys
from pathlib import Path

from google.adk.tools import ToolContext

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from checks import SKIP_DIRS, is_env_file  # noqa: E402
from sandbox import run_in_sandbox  # noqa: E402

MAX_FILES = 200
MAX_CHARS = 8000


def jail_path(sandbox: Path, path: str) -> Path | None:
    """Resolve a relative path inside the sandbox, or None if it escapes."""
    p = (path or "").replace("\\", "/").strip()
    if not p or p.startswith("/") or re.match(r"^[A-Za-z]:", p) or ".." in p.split("/"):
        return None
    root = Path(sandbox).resolve()
    target = (root / p).resolve()
    return target if target.is_relative_to(root) else None


def list_files(tool_context: ToolContext) -> dict:
    """List the files in the project under test (relative paths, max 200)."""
    root = Path(tool_context.state["sandbox"])
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if not is_env_file(f):
                files.append((Path(dirpath) / f).relative_to(root).as_posix())
    return {"files": sorted(files)[:MAX_FILES], "truncated": len(files) > MAX_FILES}


def read_file(path: str, tool_context: ToolContext) -> dict:
    """Read a text file from the project under test.

    Args:
        path: Path relative to the project root, using forward slashes (e.g. "README.md").
    """
    target = jail_path(Path(tool_context.state["sandbox"]), path)
    if target is None:
        return {"error": "path is outside the project"}
    if is_env_file(target.name):
        return {"error": "secrets files are not readable"}
    if not target.is_file():
        return {"error": f"file not found: {path}"}
    text = target.read_text(encoding="utf-8", errors="replace")
    return {"path": path, "content": text[:MAX_CHARS], "truncated": len(text) > MAX_CHARS}


def run_command(command: str, tool_context: ToolContext) -> dict:
    """Run one command in the project's clean sandbox (fresh venv, no shell).

    Args:
        command: A single command such as "pip install -r requirements.txt" or "python main.py".
    """
    try:
        argv = shlex.split(command)
    except ValueError as e:
        return {"error": f"could not parse command: {e}"}
    return run_in_sandbox(Path(tool_context.state["sandbox"]), argv)
