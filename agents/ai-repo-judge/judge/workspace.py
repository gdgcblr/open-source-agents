"""A read-only view of one submission's files. Analyzers only ever see a Workspace."""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from judge.models import SubmissionMeta

MAX_TEXT_BYTES = 1_000_000

LANGUAGES: dict[str, str] = {
    ".py": "Python",
    ".ipynb": "Jupyter",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".sh": "Shell",
    ".html": "HTML",
    ".css": "CSS",
    ".md": "Markdown",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".txt": "Text",
}
CODE_LANGUAGES = {"Python", "JavaScript", "TypeScript", "Go", "Rust", "Java", "Kotlin", "Ruby", "PHP", "C#", "Shell"}
FRONTEND_EXTS = {".html", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"}

DATA_PATH = re.compile(
    r"(?i)(^|/)(tests?|__tests__|fixtures?|samples?|sample_[\w-]+|examples?|evals?|testdata|"
    r"test_data|mocks?|benchmarks?)/|\.(diff|patch)$"
)
DOC_EXTS = (".md", ".rst", ".txt", ".adoc")

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".cache",
    ".next",
}


@dataclass(frozen=True)
class AddedLine:
    """A line added by some commit in the PR (used for history-wide secret scanning)."""

    commit: str
    path: str  # repo-relative
    line: int
    text: str


@dataclass
class Workspace:
    """Files are project-relative ("main.py"). A submission that also adds other new project folders
    (an agent plus its own MCP server under tools/, say) lists those files repo-relative with a leading
    slash ("/tools/civic-mcp/src/index.ts"), resolved against repo_root."""

    root: Path  # directory that holds the primary project's files
    project_path: str  # e.g. "agents/pdf-qa-agent"
    files: list[str]
    meta: SubmissionMeta
    changed_paths: list[str] = field(default_factory=list)  # repo-relative paths the PR touches
    changed_lines: dict[str, int] = field(default_factory=dict)  # repo-relative path -> added+deleted lines
    history: list[AddedLine] = field(default_factory=list)
    commit_messages: list[str] = field(default_factory=list)
    extra_projects: list[str] = field(default_factory=list)  # other new project folders in the same PR
    foreign_projects: list[str] = field(default_factory=list)  # existing folders (someone else's) it modifies
    repo_root: Path | None = None
    _text_cache: dict[str, str | None] = field(default_factory=dict, repr=False)
    _ast_cache: dict[str, ast.Module | None] = field(default_factory=dict, repr=False)

    @property
    def category(self) -> str:
        top = self.project_path.split("/", 1)[0]
        return top if top in ("agents", "tools") else "unknown"

    @property
    def slug(self) -> str:
        return self.project_path.rstrip("/").rsplit("/", 1)[-1]

    # ----- file access -------------------------------------------------------------------------
    def path(self, rel: str) -> Path:
        if rel.startswith("/"):
            if self.repo_root is None:
                raise ValueError(f"repo-relative path {rel!r} without repo_root")
            return self.repo_root / rel[1:]
        return self.root / rel

    def read(self, rel: str) -> str | None:
        """Text content, or None for binary/oversized/missing files."""
        if rel not in self._text_cache:
            p = self.path(rel)
            text: str | None = None
            try:
                if p.is_file() and not p.is_symlink() and p.stat().st_size <= MAX_TEXT_BYTES:
                    raw = p.read_bytes()
                    if b"\x00" not in raw[:4096]:
                        text = raw.decode("utf-8", errors="replace")
            except OSError:
                text = None
            self._text_cache[rel] = text
        return self._text_cache[rel]

    def exists(self, rel: str) -> bool:
        return rel in self.file_set

    @cached_property
    def file_set(self) -> set[str]:
        return set(self.files)

    def find(self, *names: str) -> str | None:
        """First file whose basename matches (case-insensitive), preferring the shallowest path."""
        wanted = {n.lower() for n in names}
        hits = sorted((f for f in self.files if f.rsplit("/", 1)[-1].lower() in wanted), key=lambda f: f.count("/"))
        return hits[0] if hits else None

    @staticmethod
    def language(rel: str) -> str:
        return LANGUAGES.get(os.path.splitext(rel)[1].lower(), "Other")

    def files_by_language(self, *langs: str) -> list[str]:
        return [f for f in self.files if self.language(f) in langs]

    @cached_property
    def py_files(self) -> list[str]:
        return self.files_by_language("Python")

    @cached_property
    def js_files(self) -> list[str]:
        return self.files_by_language("JavaScript", "TypeScript")

    @cached_property
    def code_files(self) -> list[str]:
        return [f for f in self.files if self.language(f) in CODE_LANGUAGES]

    @staticmethod
    def is_test_file(rel: str) -> bool:
        name = rel.rsplit("/", 1)[-1].lower()
        parts = rel.lower().split("/")
        return (
            "tests" in parts[:-1]
            or "test" in parts[:-1]
            or "__tests__" in parts[:-1]
            or name.startswith("test_")
            or name.endswith(("_test.py", "_test.go", ".test.ts", ".test.js", ".spec.ts", ".spec.js", ".test.tsx"))
        )

    @staticmethod
    def is_data_file(rel: str) -> bool:
        """Tests, fixtures, samples, evals and patches: content there is test data, not the author speaking."""
        return Workspace.is_test_file(rel) or bool(DATA_PATH.search(rel))

    @cached_property
    def source_files(self) -> list[str]:
        return [f for f in self.code_files if not self.is_test_file(f)]

    @cached_property
    def test_files(self) -> list[str]:
        return [f for f in self.code_files if self.is_test_file(f)]

    def line_count(self, rel: str) -> int:
        text = self.read(rel)
        return 0 if text is None else text.count("\n") + (0 if text.endswith("\n") or not text else 1)

    def ast(self, rel: str) -> ast.Module | None:
        if rel not in self._ast_cache:
            text = self.read(rel)
            tree = None
            if text is not None:
                try:
                    tree = ast.parse(text, filename=rel)
                except (SyntaxError, ValueError):
                    tree = None
            self._ast_cache[rel] = tree
        return self._ast_cache[rel]

    @cached_property
    def readme_path(self) -> str | None:
        return "README.md" if self.exists("README.md") else self.find("readme.md", "readme.rst", "readme.txt", "readme")

    @cached_property
    def readme(self) -> str:
        return (self.read(self.readme_path) or "") if self.readme_path else ""

    def grep(self, pattern: re.Pattern[str], files: list[str] | None = None):
        """Yield (file, line_no, line_text, match) for every regex hit."""
        for rel in files if files is not None else self.files:
            text = self.read(rel)
            if not text:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                for m in pattern.finditer(line):
                    yield rel, i, line, m


def list_local_files(root: Path) -> list[str]:
    """Walk a directory the way git would see it, skipping caches and virtualenvs."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            full = Path(dirpath) / name
            if full.is_symlink():
                continue
            out.append(full.relative_to(root).as_posix())
    return out
