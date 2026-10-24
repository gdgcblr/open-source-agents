"""Explicit execution policy. Every command the agent runs passes through here."""
from __future__ import annotations

import os
import shlex
import sys
import subprocess
from pathlib import Path

# Executable -> allowed first arguments (None = any arguments).
DEFAULT_ALLOWED: dict[str, set[str] | None] = {
    "python": {"-m"},  # further restricted below
    "pytest": None,
    "ruff": {"check", "format"},
    "mypy": None,
    "npm": {"test", "run"},
    "npx": {"tsc", "eslint", "jest", "vitest"},
    "go": {"test", "vet", "build"},
    "cargo": {"test", "check", "build", "clippy"},
}
PYTHON_MODULES = {"pytest", "unittest", "ruff", "mypy", "compileall", "py_compile"}
NPM_RUN_SCRIPTS = {"test", "lint", "build", "typecheck", "check"}
FORBIDDEN_CHARS = set("|&;<>`$\n\r")
# Never hand repository code the user's credentials.
SECRET_ENV = ("GITHUB_TOKEN", "GH_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY")


class PolicyError(Exception):
    pass


def check_command(command: str, extra_allowed: list[str] | None = None) -> list[str]:
    """Validate a command string and return argv. Raises PolicyError if not allowed."""
    if any(c in FORBIDDEN_CHARS for c in command):
        raise PolicyError("Shell operators (| & ; < > ` $) are not allowed.")
    try:
        argv = shlex.split(command, posix=True)
    except ValueError as e:
        raise PolicyError(f"Could not parse command: {e}") from e
    if not argv:
        raise PolicyError("Empty command.")
    exe = Path(argv[0]).name.lower().removesuffix(".exe").removesuffix(".cmd")
    if exe in ("python3", "py"):
        exe = "python"
    if extra_allowed and exe in {e.lower() for e in extra_allowed}:
        return argv
    if exe not in DEFAULT_ALLOWED:
        raise PolicyError(f"'{exe}' is not in the execution allowlist.")
    allowed_first = DEFAULT_ALLOWED[exe]
    first = argv[1] if len(argv) > 1 else ""
    if allowed_first is not None and first not in allowed_first:
        raise PolicyError(f"'{exe} {first}' is not allowed.")
    if exe == "python" and (len(argv) < 3 or argv[2] not in PYTHON_MODULES):
        raise PolicyError(f"python -m only allows: {', '.join(sorted(PYTHON_MODULES))}.")
    if exe == "npm" and first == "run" and (len(argv) < 3 or argv[2] not in NPM_RUN_SCRIPTS):
        raise PolicyError(f"npm run only allows: {', '.join(sorted(NPM_RUN_SCRIPTS))}.")
    return argv


def run_command(command: str, cwd: Path, timeout: int, extra_allowed: list[str] | None = None,
                python_exe: str | None = None) -> dict:
    """Run an allowlisted command without a shell. Returns {command, exit_code, output}."""
    argv = check_command(command, extra_allowed)
    if Path(argv[0]).name.lower() in ("python", "python3", "py", "python.exe"):
        argv[0] = python_exe or sys.executable  # agent's interpreter unless config sets python_executable
    env = {k: v for k, v in os.environ.items() if k.upper() not in SECRET_ENV}
    env["PYTHONDONTWRITEBYTECODE"] = "1"  # keep bytecode out of the reported changes
    try:
        p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout,
                           shell=False, encoding="utf-8", errors="replace")
        out = (p.stdout or "") + (p.stderr or "")
        return {"command": command, "exit_code": p.returncode, "output": out[-6000:]}
    except subprocess.TimeoutExpired:
        return {"command": command, "exit_code": -1, "output": f"Timed out after {timeout}s."}
    except FileNotFoundError:
        return {"command": command, "exit_code": -1, "output": f"'{argv[0]}' is not installed."}
