"""Small helpers for looking at a project folder on disk."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

IGNORED_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "runs", ".idea", ".vscode", "dist", "build",
}
README_NAMES = ("README.md", "readme.md", "Readme.md", "README.rst", "README.txt", "README")
MANIFEST_NAMES = (
    "requirements.txt", "requirements-dev.txt", "pyproject.toml", "setup.py", "setup.cfg",
    "Pipfile", "environment.yml", "package.json", ".env.example",
)


def find_readme(project_dir: Path) -> Optional[Path]:
    for name in README_NAMES:
        p = project_dir / name
        if p.is_file():
            return p
    return None


def read_text(path: Path, limit: int = 200_000) -> Optional[str]:
    """Read a text file, or None if it is missing or looks binary."""
    try:
        data = path.read_bytes()[:limit]
    except OSError:
        return None
    if b"\x00" in data[:4096]:
        return None
    return data.decode("utf-8", errors="replace")


def numbered(text: str, start: int = 1) -> str:
    lines = text.splitlines()
    width = len(str(start + len(lines)))
    return "\n".join(f"{i:>{width}} | {line}" for i, line in enumerate(lines, start))


def list_files(project_dir: Path, limit: int = 300) -> list[str]:
    """Relative paths of project files, skipping virtualenvs, caches and VCS folders."""
    out: list[str] = []
    for p in sorted(project_dir.rglob("*")):
        rel = p.relative_to(project_dir)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        if p.is_file():
            out.append(rel.as_posix())
            if len(out) >= limit:
                break
    return out


def manifests(project_dir: Path) -> dict[str, str]:
    """Dependency and config files a newcomer would look at, keyed by name."""
    found = {}
    for name in MANIFEST_NAMES:
        text = read_text(project_dir / name, limit=20_000)
        if text is not None:
            found[name] = text
    return found


def safe_path(project_dir: Path, rel: str) -> Path:
    """Resolve rel inside project_dir, refusing anything that escapes it."""
    root = project_dir.resolve()
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes the project: {rel}")
    return target
