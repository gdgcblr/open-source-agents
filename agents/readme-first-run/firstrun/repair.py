"""Applying proposed edits to a copy of the project and diffing the result."""

from __future__ import annotations

import difflib
import shutil
from pathlib import Path

from .models import Edit
from .project import IGNORED_DIRS, read_text, safe_path

MAX_EDIT_CHARS = 20_000


class EditError(ValueError):
    pass


def copy_project(src: Path, dst: Path) -> Path:
    """Copy a project the way a fresh clone would look: no venvs, caches or .git."""
    def ignore(_dir, names):
        return [n for n in names if n in IGNORED_DIRS or n.endswith(".pyc")]

    shutil.copytree(src, dst, ignore=ignore, symlinks=True)
    return dst


def validate_edits(project_dir: Path, edits: list[Edit]) -> list[str]:
    """Return a list of problems. An empty list means every edit can be applied."""
    problems = []
    if not edits:
        return problems
    for i, e in enumerate(edits, 1):
        label = f"edit {i} ({e.path})"
        try:
            target = safe_path(project_dir, e.path)
        except ValueError as exc:
            problems.append(f"{label}: {exc}")
            continue
        rel_parts = Path(e.path).parts
        if any(part in IGNORED_DIRS for part in rel_parts):
            problems.append(f"{label}: cannot edit inside {rel_parts[0]}")
            continue
        if len(e.new) > MAX_EDIT_CHARS or len(e.old) > MAX_EDIT_CHARS:
            problems.append(f"{label}: edit is too large to be a minimal fix")
            continue
        if not e.old:
            continue  # append or create, always possible
        if not target.is_file():
            problems.append(f"{label}: file does not exist, so 'old' text cannot match")
            continue
        text = read_text(target)
        if text is None:
            problems.append(f"{label}: not a text file")
            continue
        count = text.count(e.old)
        if count == 0:
            problems.append(f"{label}: 'old' text not found in file")
        elif count > 1:
            problems.append(f"{label}: 'old' text appears {count} times, make it unique")
    return problems


def apply_edits(project_dir: Path, edits: list[Edit]) -> None:
    problems = validate_edits(project_dir, edits)
    if problems:
        raise EditError("; ".join(problems))
    for e in edits:
        target = safe_path(project_dir, e.path)
        if not e.old:
            existing = target.read_text(encoding="utf-8") if target.is_file() else ""
            if existing and not existing.endswith("\n"):
                existing += "\n"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(existing + e.new, encoding="utf-8")
        else:
            text = target.read_text(encoding="utf-8")
            target.write_text(text.replace(e.old, e.new, 1), encoding="utf-8")


def _text_files(root: Path) -> dict[str, str]:
    files = {}
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if any(part in IGNORED_DIRS for part in rel.parts) or not p.is_file():
            continue
        text = read_text(p)
        if text is not None:
            files[rel.as_posix()] = text
    return files


def unified_diff(original: Path, patched: Path) -> str:
    """Git style diff (a/ and b/ prefixes) so it can be applied with `git apply`."""
    before, after = _text_files(original), _text_files(patched)
    chunks = []
    for rel in sorted(set(before) | set(after)):
        a, b = before.get(rel), after.get(rel)
        if a == b:
            continue
        a_lines = (a or "").splitlines(keepends=True)
        b_lines = (b or "").splitlines(keepends=True)
        if a_lines and not a_lines[-1].endswith("\n"):
            a_lines[-1] += "\n\\ No newline at end of file\n"
        if b_lines and not b_lines[-1].endswith("\n"):
            b_lines[-1] += "\n\\ No newline at end of file\n"
        header = f"diff --git a/{rel} b/{rel}\n"
        if a is None:
            header += "new file mode 100644\n"
        fromfile = "/dev/null" if a is None else f"a/{rel}"
        tofile = "/dev/null" if b is None else f"b/{rel}"
        body = "".join(difflib.unified_diff(a_lines, b_lines, fromfile=fromfile, tofile=tofile))
        chunks.append(header + body)
    return "".join(chunks)
