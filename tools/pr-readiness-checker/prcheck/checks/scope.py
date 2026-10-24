"""G1-G3: what the pull request would change, compared with the base branch."""

from __future__ import annotations

from pathlib import PurePosixPath

from .. import git
from ..context import ProjectContext, SkipCheck
from ..models import Severity
from ..registry import check, finding

GROUP = "scope"
_MAX_LISTED = 8


def _project_prefix(ctx: ProjectContext) -> str:
    if ctx.relative_path is None:
        raise SkipCheck("Project is not inside the repository root.")
    return str(ctx.relative_path) + "/"


def _index_file(ctx: ProjectContext) -> str | None:
    return f"{ctx.category}/README.md" if ctx.category else None


def _root_manifests(ctx: ProjectContext, changed: list[str]) -> list[str]:
    return [p for p in changed if "/" not in p and p in ctx.rules.manifests]


@check("G1", group=GROUP, title="Changes stay inside the project folder", severity=Severity.ERROR,
       rule="CONTRIBUTING.md > Scoping Your Pull Request")
def changes_in_scope(ctx: ProjectContext):
    scope = ctx.require_scope()
    prefix = _project_prefix(ctx)
    index = _index_file(ctx)
    root_manifests = set(_root_manifests(ctx, scope.changed))  # reported by G2

    outside = [p for p in scope.changed if not p.startswith(prefix) and p != index and p not in root_manifests]
    if outside:
        listed = ", ".join(outside[:_MAX_LISTED]) + (f" (+{len(outside) - _MAX_LISTED} more)"
                                                     if len(outside) > _MAX_LISTED else "")
        yield finding("G1", f"{len(outside)} file(s) changed outside {prefix} compared with {scope.base}: {listed}. "
                            "Revert them or move them into your folder.")

    if index and index in scope.changed and ctx.git_root is not None:
        added, removed = git.numstat(ctx.git_root, scope.merge_base, index)
        if added > ctx.rules.max_index_lines_added or removed > ctx.rules.max_index_lines_removed:
            yield finding("G1", f"{index} changed by +{added}/-{removed} lines; only one index-table row "
                                "should be added.", severity=Severity.WARN)


@check("G2", group=GROUP, title="No dependencies added at the repository root", severity=Severity.ERROR,
       rule="CONTRIBUTING.md > Scoping Your Pull Request (do not modify root build files)")
def no_root_manifests(ctx: ProjectContext):
    scope = ctx.require_scope()
    for path in _root_manifests(ctx, scope.changed):
        yield finding("G2", f"Root file '{path}' changed; keep dependencies in your project's own manifest.")


@check("G3", group=GROUP, title="Folder name is not already taken upstream", severity=Severity.WARN,
       rule="CONTRIBUTING.md > Directory & Naming Rules #4 (uniqueness)")
def name_unique(ctx: ProjectContext):
    scope = ctx.require_scope()
    prefix = _project_prefix(ctx).rstrip("/")
    if ctx.git_root is None or len(PurePosixPath(prefix).parts) != 2:
        raise SkipCheck("Project location is not <category>/<slug> (see S1).")
    if git.path_exists_at(ctx.git_root, scope.base, prefix):
        yield finding("G3", f"'{prefix}' already exists on {scope.base}. Fine if you are updating your own "
                            "project; otherwise pick a more specific name.")
