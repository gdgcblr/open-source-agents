"""Deterministic mock heuristic.

Turns a :class:`~commit_assistant.diff_parser.DiffSummary` into a
Conventional Commits message with no network call. Every rule here is
pure and documented so the same diff always yields the same message.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from .diff_parser import ADDED, DELETED, MODIFIED, RENAMED, DiffSummary, FileChange

# Soft cap for the subject line per Conventional Commits guidance.
SUBJECT_MAX = 72
# Most bullets we emit before collapsing the rest into a summary line.
MAX_BULLETS = 10

# Extensions / locations treated as documentation.
_DOC_EXTS = {".md", ".rst", ".txt", ".adoc"}
# Dependency / build manifests that make a change a chore.
_MANIFEST_NAMES = {
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "dockerfile",
    ".gitignore",
    ".dockerignore",
    "makefile",
}
_CI_DIRS = (".github/", ".gitlab/", "ci/")


@dataclass
class CommitMessage:
    """A structured Conventional Commits message."""

    type: str
    subject: str
    scope: Optional[str] = None
    body_bullets: List[str] = field(default_factory=list)


def _is_test_path(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    base = os.path.basename(p)
    if p.startswith("tests/") or p.startswith("test/") or "/tests/" in p or "/test/" in p:
        return True
    return base.startswith("test_") or base.endswith("_test.py")


def _is_doc_path(fc: FileChange) -> bool:
    p = fc.path.replace("\\", "/").lower()
    # A manifest (e.g. requirements.txt) is a chore, not documentation,
    # even though it ends in a doc-like extension.
    if _is_manifest_path(fc.path):
        return False
    if p.startswith("docs/") or "/docs/" in p:
        return True
    return fc.ext in _DOC_EXTS


def _is_manifest_path(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    base = os.path.basename(p)
    if base in _MANIFEST_NAMES:
        return True
    if p.endswith((".yml", ".yaml")) and p.startswith(_CI_DIRS):
        return True
    return False


def _decide_type(summary: DiffSummary) -> str:
    """Pick the Conventional Commits type (first matching rule wins)."""
    files = summary.files

    # 1. Everything is a test file.
    if files and all(_is_test_path(f.path) for f in files):
        return "test"

    # 2. Everything is documentation.
    if files and all(_is_doc_path(f) for f in files):
        return "docs"

    # 3. Everything is a dependency/build manifest.
    if files and all(_is_manifest_path(f.path) for f in files):
        return "chore"

    # 4. Only deletions (no new files, net-negative) -> refactor.
    if files and all(f.change_type == DELETED for f in files):
        return "refactor"

    # 5. Any brand-new source file -> feat.
    if any(f.change_type == ADDED for f in files):
        return "feat"

    # 6. Existing source modified: look for a bug signal, else size-based.
    if any("fix" in f.path.lower() or "bug" in f.path.lower() for f in files):
        return "fix"
    if summary.total_added - summary.total_removed > 10:
        return "feat"
    return "chore"


def _decide_scope(summary: DiffSummary) -> Optional[str]:
    """Common top-level dir, or the single file's stem, else ``None``."""
    files = summary.files
    if not files:
        return None

    if len(files) == 1:
        path = files[0].path.replace("\\", "/")
        if "/" in path:
            return path.split("/", 1)[0]
        # Single file at the repo root -> use its stem as the scope.
        return os.path.splitext(os.path.basename(path))[0] or None

    tops = set()
    for f in files:
        path = f.path.replace("\\", "/")
        tops.add(path.split("/", 1)[0] if "/" in path else path)
    if len(tops) == 1:
        top = next(iter(tops))
        # A shared top-level *file* is not a useful scope.
        return top if "." not in os.path.basename(top) else None
    return None


def _verb(change_type: str) -> str:
    return {
        ADDED: "add",
        DELETED: "delete",
        MODIFIED: "update",
        RENAMED: "rename",
    }.get(change_type, "update")


def _build_subject(summary: DiffSummary, ctype: str) -> str:
    """Deterministic imperative summary derived from the change set."""
    files = summary.files
    if not files:
        return "update repository"

    if len(files) == 1:
        fc = files[0]
        name = os.path.basename(fc.path)
        verb = _verb(fc.change_type)
        if ctype == "docs":
            return f"update {name} documentation"
        if fc.change_type == ADDED:
            stem = os.path.splitext(name)[0]
            return f"add {stem} module" if fc.ext == ".py" else f"add {name}"
        return f"{verb} {name}"

    added = sum(1 for f in files if f.change_type == ADDED)
    deleted = sum(1 for f in files if f.change_type == DELETED)
    n = len(files)
    if added == n:
        return f"add {n} new files"
    if deleted == n:
        return f"remove {n} files"
    if ctype == "docs":
        return f"update {n} documentation files"
    if ctype == "test":
        return f"update {n} test files"
    return f"update {n} files"


def _cap(text: str, limit: int = SUBJECT_MAX) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _build_bullets(summary: DiffSummary) -> List[str]:
    bullets: List[str] = []
    for fc in summary.files[:MAX_BULLETS]:
        bullets.append(f"{_verb(fc.change_type)} {fc.path} (+{fc.added}/-{fc.removed})")
    remaining = summary.file_count - MAX_BULLETS
    if remaining > 0:
        bullets.append(f"…and {remaining} more file(s)")
    return bullets


def build_message(summary: DiffSummary, no_body: bool = False) -> CommitMessage:
    """Build a :class:`CommitMessage` from ``summary`` using the heuristic."""
    ctype = _decide_type(summary)
    scope = _decide_scope(summary)
    subject = _cap(_build_subject(summary, ctype))
    bullets = [] if no_body else _build_bullets(summary)
    return CommitMessage(type=ctype, subject=subject, scope=scope, body_bullets=bullets)


def render(msg: CommitMessage) -> str:
    """Render a :class:`CommitMessage` to Conventional Commits text."""
    header = f"{msg.type}({msg.scope}): {msg.subject}" if msg.scope else f"{msg.type}: {msg.subject}"
    if not msg.body_bullets:
        return header
    body = "\n".join(f"- {b}" for b in msg.body_bullets)
    return f"{header}\n\n{body}"
