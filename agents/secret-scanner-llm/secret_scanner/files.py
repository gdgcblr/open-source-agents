"""File selection: skip rules, .secretscanignore, test-path heuristics."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path, PurePosixPath

MAX_BYTES = 1_000_000
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", ".mypy_cache",
    ".pytest_cache", ".idea", ".vscode",
}
LOCKFILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "Pipfile.lock",
    "Cargo.lock", "Gemfile.lock", "composer.lock", "go.sum", "bun.lockb", "npm-shrinkwrap.json",
}
IGNORE_FILE = ".secretscanignore"
INLINE_IGNORE = "secretscan:ignore"

_TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "fixtures", "fixture", "testdata", "mocks", "e2e"}


import re as _re

INJECTION_RE = _re.compile(
    r"(ignore|disregard|forget)\W+(all\W+|any\W+)?(the\W+)?(previous|prior|above|earlier)\W+(instructions?|prompts?|rules?)"
    r"|mark\W+(everything|all|this|these)\W+(as\W+)?(a\W+)?(false.?positive|placeholder|test.?fixture|safe)"
    r"|(system|developer)\s+(prompt|message)|you\s+are\s+now\b|\bnew\s+instructions?\b"
    r"|do\s+not\s+(report|flag)\s+(this|these|any)",
    _re.I,
)


def looks_like_injection(text: str) -> bool:
    return bool(INJECTION_RE.search(text))


def is_test_path(rel: str) -> bool:
    p = PurePosixPath(rel.replace(os.sep, "/"))
    if any(part.lower() in _TEST_DIRS for part in p.parts[:-1]):
        return True
    n = p.name.lower()
    return (
        n.startswith("test_") or n == "conftest.py" or ".test." in n or ".spec." in n
        or n.rsplit(".", 1)[0].endswith(("_test", "_spec"))
    )


class IgnoreRules:
    """Minimal gitignore-like matcher (no negation). `dir/` , `*.ext`, `path/glob`."""

    def __init__(self, patterns: list[str] | None = None):
        self.patterns = [p.strip() for p in (patterns or []) if p.strip() and not p.strip().startswith("#")]

    @classmethod
    def load(cls, root: Path) -> "IgnoreRules":
        f = root / IGNORE_FILE
        if f.is_file():
            try:
                return cls(f.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                pass
        return cls([])

    def matches(self, rel: str) -> bool:
        rel = rel.replace(os.sep, "/")
        parts = rel.split("/")
        for pat in self.patterns:
            if pat.endswith("/"):
                if pat.rstrip("/") in parts[:-1]:
                    return True
            elif "/" in pat:
                if fnmatch.fnmatch(rel, pat.lstrip("/")) or fnmatch.fnmatch(rel, pat.lstrip("/") + "/*"):
                    return True
            elif any(fnmatch.fnmatch(part, pat) for part in parts):
                return True
        return False


def skip_reason(name: str, size: int | None, head: bytes | None) -> str | None:
    if name in LOCKFILES:
        return "lockfile"
    if size is not None and size > MAX_BYTES:
        return "too_large"
    if head is not None and b"\x00" in head:
        return "binary"
    return None
