"""Load simple project-local environment settings without third-party packages."""

from __future__ import annotations

import os
import re
from pathlib import Path

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_project_env() -> None:
    """Load .env from the project directory; existing process variables win."""
    project_root = Path(__file__).resolve().parents[2]
    env_file = project_root / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        name, value = name.strip(), value.strip()
        if not _ENV_NAME.fullmatch(name) or name in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[name] = value
