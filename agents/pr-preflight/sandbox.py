"""Harness: temp copy of a project + fresh venv + safe subprocess (shell=False)."""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

EXCLUDE = {".venv", "venv", "node_modules", ".git", "__pycache__", ".env"}
MAX_OUT = 3000
PREFIX = "preflight_"
SECRET_ENV_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


def _ignore(_dir, names):
    return [n for n in names
            if n in EXCLUDE or (n.startswith(".env.") and n != ".env.example")]


def create_sandbox(project_path) -> Path:
    src = Path(project_path).resolve()
    sandbox = Path(tempfile.mkdtemp(prefix=PREFIX)) / "project"
    shutil.copytree(src, sandbox, ignore=_ignore)
    return sandbox


def _venv_python(sandbox: Path) -> Path:
    venv = sandbox / ".venv"
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv)],
                       check=True, capture_output=True, timeout=180)
    return py


def _child_env(sandbox: Path) -> dict:
    """Environment for sandboxed commands: no API keys/tokens leak in."""
    env = {k: v for k, v in os.environ.items()
           if not any(h in k.upper() for h in SECRET_ENV_HINTS)}
    venv = sandbox / ".venv"
    bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    env["VIRTUAL_ENV"] = str(venv)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return env


def _resolve(sandbox: Path, command: list[str]) -> list[str]:
    first, rest = command[0].lower(), command[1:]
    if first in ("python", "python3", "py"):
        return [str(_venv_python(sandbox))] + rest
    if first in ("pip", "pip3"):
        return [str(_venv_python(sandbox)), "-m", "pip"] + rest
    if first == "pytest":
        return [str(_venv_python(sandbox)), "-m", "pytest"] + rest
    exe = shutil.which(command[0])  # e.g. npm -> npm.cmd on Windows
    return [exe or command[0]] + rest


def _tail(text) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    return text[-MAX_OUT:]


def run_in_sandbox(sandbox: Path, command: list[str], timeout: int = 120) -> dict:
    sandbox = Path(sandbox)
    if not command:
        return {"exit_code": 2, "stdout": "", "stderr": "empty command", "timed_out": False}
    try:
        cmd = _resolve(sandbox, command)
        proc = subprocess.run(cmd, cwd=sandbox, shell=False, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, env=_child_env(sandbox))
        return {"exit_code": proc.returncode, "stdout": _tail(proc.stdout),
                "stderr": _tail(proc.stderr), "timed_out": False}
    except subprocess.TimeoutExpired as e:
        return {"exit_code": -1, "stdout": _tail(e.stdout),
                "stderr": _tail(e.stderr) + f"\n[timed out after {timeout}s]",
                "timed_out": True}
    except (FileNotFoundError, subprocess.CalledProcessError, OSError) as e:
        return {"exit_code": 127, "stdout": "", "stderr": f"{type(e).__name__}: {e}",
                "timed_out": False}


def _force_remove(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)  # Windows read-only files (e.g. .git objects)
    func(path)


def cleanup_sandbox(sandbox) -> None:
    root = Path(sandbox).parent
    if root.name.startswith(PREFIX) and root.exists():  # never delete anything else
        shutil.rmtree(root, onexc=_force_remove)


if __name__ == "__main__":
    s = create_sandbox(sys.argv[1] if len(sys.argv) > 1 else "evals/fixtures/good_project")
    try:
        print(run_in_sandbox(s, ["python", "main.py"]))
    finally:
        cleanup_sandbox(s)
