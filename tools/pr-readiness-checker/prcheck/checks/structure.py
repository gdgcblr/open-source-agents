"""S1-S4: where the project lives and what it is called."""

from __future__ import annotations

import re

from ..context import ProjectContext, SkipCheck
from ..models import Severity
from ..registry import check, finding

GROUP = "structure"


@check("S1", group=GROUP, title="Folder is directly under agents/ or tools/", severity=Severity.ERROR,
       rule="CONTRIBUTING.md > Directory & Naming Rules #1")
def folder_location(ctx: ProjectContext):
    if ctx.repo_root is None:
        raise SkipCheck("Not inside the open-source-ai repository, so the location can't be checked.")
    rel = ctx.relative_path
    allowed = " or ".join(f"{c}/<project-slug>/" for c in ctx.rules.categories)
    if rel is None or len(rel.parts) != 2 or rel.parts[0] not in ctx.rules.categories:
        yield finding("S1", f"Project is at '{ctx.display_path}'; it must be {allowed}.")


@check("S2", group=GROUP, title="Folder name is lowercase kebab-case", severity=Severity.ERROR,
       rule="CONTRIBUTING.md > Directory & Naming Rules #2")
def kebab_case(ctx: ProjectContext):
    if not re.fullmatch(ctx.rules.slug_pattern, ctx.slug):
        suggestion = re.sub(r"[^a-z0-9]+", "-", re.sub(r"(?<=[a-z0-9])([A-Z])", r"-\1", ctx.slug).lower()).strip("-")
        yield finding("S2", f"'{ctx.slug}' is not lowercase kebab-case; try '{suggestion or 'my-descriptive-name'}'.")


@check("S3", group=GROUP, title="Folder name is descriptive, not generic", severity=Severity.ERROR,
       rule="CONTRIBUTING.md > Directory & Naming Rules #3")
def descriptive_name(ctx: ProjectContext):
    if ctx.slug.lower().replace("_", "-") in ctx.rules.generic_names:
        yield finding("S3", f"'{ctx.slug}' is too generic; pick a name that says what the project does.")


@check("S4", group=GROUP, title="Project has its own .gitignore", severity=Severity.WARN,
       rule="CONTRIBUTING.md > Step 5 (copy template/.gitignore)")
def has_gitignore(ctx: ProjectContext):
    if ".gitignore" not in ctx.files:
        yield finding("S4", "No .gitignore in the project folder; copy template/.gitignore.")
