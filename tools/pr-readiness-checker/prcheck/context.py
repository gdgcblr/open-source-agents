"""ProjectContext: everything checks need, gathered once per run.

Checks only read from the context. New inputs (a sandboxed install run, a
per-repo rules file, a PR diff from the GitHub API) are added here so existing
checks keep working unchanged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import cached_property
from importlib import resources
from pathlib import Path, PurePosixPath

from . import git, markdown
from .rules import Rules


class SkipCheck(Exception):
    """Raised by a check that cannot run in this context; the message is shown to the user."""


@dataclass
class ScopeInfo:
    base: str
    merge_base: str
    changed: list[str]  # repo-relative posix paths


@dataclass
class ProjectContext:
    project_dir: Path
    rules: Rules
    repo_root: Path | None
    git_root: Path | None
    files: list[str]  # project-relative posix paths that would be committed
    file_mode: str  # "git" or "filesystem"
    template_text: str
    template_source: str  # "repo" or "bundled"
    scope: ScopeInfo | None = None
    scope_skip_reason: str | None = None
    bytes_scanned: int = 0
    files_scanned: int = 0
    _text_cache: dict[str, str | None] = field(default_factory=dict)

    # --- identity -------------------------------------------------------------

    @property
    def slug(self) -> str:
        return self.project_dir.name

    @cached_property
    def relative_path(self) -> PurePosixPath | None:
        """Project path relative to the repository root, e.g. tools/my-tool."""
        if self.repo_root is None:
            return None
        try:
            return PurePosixPath(self.project_dir.relative_to(self.repo_root).as_posix())
        except ValueError:
            return None

    @property
    def category(self) -> str | None:
        rel = self.relative_path
        if rel is not None and len(rel.parts) >= 1 and rel.parts[0] in self.rules.categories:
            return rel.parts[0]
        return None

    @property
    def display_path(self) -> str:
        return str(self.relative_path) if self.relative_path else self.project_dir.as_posix()

    # --- files ------------------------------------------------------------------

    def read_text(self, rel: str) -> str | None:
        """Text of a project file, or None if missing, binary, or too large to scan."""
        if rel in self._text_cache:
            return self._text_cache[rel]
        path = self.project_dir / rel
        text: str | None = None
        try:
            if path.is_file() and path.stat().st_size <= self.rules.max_scan_bytes:
                data = path.read_bytes()
                if b"\0" not in data[:8192]:
                    text = data.decode("utf-8", errors="replace")
                    self.files_scanned += 1
                    self.bytes_scanned += len(data)
        except OSError:
            text = None
        self._text_cache[rel] = text
        return text

    @property
    def readme_path(self) -> str | None:
        wanted = self.rules.readme_file.lower()
        for rel in self.files:
            if rel.lower() == wanted:
                return rel
        return None

    @cached_property
    def readme(self) -> markdown.ParsedMarkdown | None:
        rel = self.readme_path
        if rel is None:
            return None
        text = self.read_text(rel)
        return markdown.parse(text) if text is not None else None

    @cached_property
    def template(self) -> markdown.ParsedMarkdown:
        return markdown.parse(self.template_text)

    def require_readme(self) -> markdown.ParsedMarkdown:
        if self.readme is None:
            raise SkipCheck(f"No {self.rules.readme_file} to inspect (see D1).")
        return self.readme

    def require_scope(self) -> ScopeInfo:
        if self.scope is None:
            raise SkipCheck(self.scope_skip_reason or "Scope checks need git and a base branch.")
        return self.scope


# --- building a context ---------------------------------------------------------


def find_repo_root(start: Path, rules: Rules) -> Path | None:
    """Nearest parent that looks like the open-source-ai repo (has template/ and the categories)."""
    for candidate in [start, *start.parents]:
        if (candidate / "template" / "README.md").is_file() and all(
            (candidate / category).is_dir() for category in rules.categories
        ):
            return candidate
    return None


def _walk_files(project_dir: Path, rules: Rules) -> list[str]:
    """Filesystem fallback when git is unavailable. Junk folders are listed, not descended."""
    found: list[str] = []
    for root, dirs, files in os.walk(project_dir):
        rel_root = Path(root).relative_to(project_dir)
        for name in list(dirs):
            if name == ".git":
                dirs.remove(name)
            elif name in rules.junk_dirs:
                dirs.remove(name)
                found.append((rel_root / name).as_posix() + "/")
        found.extend((rel_root / name).as_posix() for name in files)
    return sorted(found)


def _load_template(repo_root: Path | None) -> tuple[str, str]:
    if repo_root is not None:
        path = repo_root / "template" / "README.md"
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace"), "repo"
    bundled = resources.files("prcheck").joinpath("data/template_readme.md")
    return bundled.read_text(encoding="utf-8"), "bundled"


def _resolve_scope(git_root: Path, rules: Rules, base: str | None) -> tuple[ScopeInfo | None, str | None]:
    candidates = [base] if base else list(rules.default_bases)
    chosen = next((ref for ref in candidates if git.ref_exists(git_root, ref)), None)
    if chosen is None:
        if base:
            return None, f"Base ref '{base}' not found. Run `git fetch upstream` or pass another --base."
        tried = ", ".join(candidates)
        return None, f"No base branch found (tried {tried}). Pass --base to enable scope checks."
    try:
        since = git.merge_base(git_root, chosen)
        changed = git.changed_files(git_root, since)
    except git.GitError as exc:
        return None, f"Could not compare with {chosen}: {exc}"
    return ScopeInfo(base=chosen, merge_base=since, changed=changed), None


def build_context(project_dir: Path, rules: Rules, *, base: str | None = None, use_git: bool = True) -> ProjectContext:
    project_dir = project_dir.resolve()
    repo_root = find_repo_root(project_dir, rules)
    git_root = git.toplevel(project_dir) if use_git else None

    files: list[str] | None = None
    file_mode = "filesystem"
    if git_root is not None:
        try:
            files = git.files_to_commit(project_dir)
            file_mode = "git"
        except git.GitError:
            files = None
    if files is None:
        files = _walk_files(project_dir, rules)

    template_text, template_source = _load_template(repo_root)

    scope: ScopeInfo | None = None
    scope_skip: str | None
    if not use_git:
        scope_skip = "Git checks disabled (--no-git)."
    elif git_root is None:
        scope_skip = "Not inside a git repository."
    elif repo_root is None:
        scope_skip = "Not inside the open-source-ai repository."
    elif os.path.normcase(git_root) != os.path.normcase(repo_root):
        scope_skip = "The git repository root is not the open-source-ai root."
    else:
        scope, scope_skip = _resolve_scope(git_root, rules, base)

    return ProjectContext(
        project_dir=project_dir,
        rules=rules,
        repo_root=repo_root,
        git_root=git_root,
        files=files,
        file_mode=file_mode,
        template_text=template_text,
        template_source=template_source,
        scope=scope,
        scope_skip_reason=scope_skip,
    )
