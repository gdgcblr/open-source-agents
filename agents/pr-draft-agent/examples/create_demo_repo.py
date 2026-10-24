"""Create a disposable Git repository for an offline PR Draft Agent demo.

The repository is always created in a fresh temporary directory outside this
checkout, with a local Git identity. Nothing is written to an existing path.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

CONFIG_BEFORE = """\
import json


def load_config(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
"""

CONFIG_AFTER = """\
import json
import os


def load_config(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
"""

TEMPLATE = """\
## Summary

## Why

## Testing

## Suggested checks
"""


def _git(root: Path, *args: str) -> None:
    # Git environment overrides can redirect even `git -C` into another repo.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_AUTHOR_NAME="PR Draft Demo",
        GIT_AUTHOR_EMAIL="demo@example.invalid",
        GIT_COMMITTER_NAME="PR Draft Demo",
        GIT_COMMITTER_EMAIL="demo@example.invalid",
    )
    subprocess.run(
        [
            "git", "-c", f"core.hooksPath={os.devnull}",
            "-c", "commit.gpgSign=false", "-c", "tag.gpgSign=false",
            "-c", "init.templateDir=", "-C", str(root), *args,
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    checkout = next(
        (path for path in (project, *project.parents) if (path / ".git").exists()), project
    )
    temporary_parent = Path(tempfile.gettempdir()).resolve()
    if temporary_parent.is_relative_to(checkout):
        temporary_parent = Path("/tmp").resolve()
    if temporary_parent.is_relative_to(checkout):
        raise RuntimeError("Choose a system temporary directory outside this checkout.")
    root = Path(tempfile.mkdtemp(prefix="pr-draft-demo-", dir=temporary_parent))
    _git(root, "init", "-b", "main", "--quiet")
    _git(root, "config", "user.name", "PR Draft Demo")
    _git(root, "config", "user.email", "demo@example.invalid")

    (root / "config_loader.py").write_text(CONFIG_BEFORE, encoding="utf-8")
    (root / ".github").mkdir()
    (root / ".github" / "PULL_REQUEST_TEMPLATE.md").write_text(TEMPLATE, encoding="utf-8")
    _git(root, "add", "config_loader.py", ".github/PULL_REQUEST_TEMPLATE.md")
    _git(root, "commit", "-m", "Add configuration loader", "--quiet")

    (root / "config_loader.py").write_text(CONFIG_AFTER, encoding="utf-8")
    _git(root, "add", "config_loader.py")

    print(f"Demo repository: {root}")
    print(f"Inspect it with: uv run python -m pr_draft_agent --repo {root} --check")


if __name__ == "__main__":
    main()
