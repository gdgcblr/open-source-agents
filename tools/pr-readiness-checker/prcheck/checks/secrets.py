"""X1-X4: secrets and files that must never be committed."""

from __future__ import annotations

import re
from fnmatch import fnmatch
from pathlib import PurePosixPath

from .. import secret_patterns
from ..context import ProjectContext
from ..models import Severity
from ..registry import check, finding

GROUP = "secrets"

_CODE_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".rb",
                  ".php", ".cs", ".sh", ".ipynb"}
_ENV_USAGE = re.compile(
    r"os\.getenv|os\.environ|load_dotenv|process\.env|Deno\.env|import\.meta\.env|os\.Getenv|std::env|"
    r"System\.getenv|ENV\[|getenv\("
)


def _is_junk(ctx: ProjectContext, rel: str) -> bool:
    return any(part in ctx.rules.junk_dirs for part in PurePosixPath(rel.rstrip("/")).parts)


def _scannable(ctx: ProjectContext) -> list[str]:
    return [rel for rel in ctx.files if not rel.endswith("/") and not _is_junk(ctx, rel)]


@check("X1", group=GROUP, title="No secret or credential files", severity=Severity.ERROR,
       rule="CONTRIBUTING.md > Zero Secrets Policy; PR checklist 'Secrets & Security'")
def forbidden_files(ctx: ProjectContext):
    for rel in _scannable(ctx):
        name = PurePosixPath(rel).name
        if name in ctx.rules.allowed_names:
            continue
        if name in ctx.rules.forbidden_names or any(fnmatch(name, glob) for glob in ctx.rules.forbidden_globs):
            yield finding("X1", f"'{rel}' must not be committed; delete it or add it to .gitignore.", file=rel)


@check("X2", group=GROUP, title="No API keys or tokens in file contents", severity=Severity.ERROR,
       rule="CONTRIBUTING.md > Zero Secrets Policy")
def leaked_secrets(ctx: ProjectContext):
    for rel in _scannable(ctx):
        text = ctx.read_text(rel)
        if not text:
            continue
        for match in secret_patterns.scan(text):
            yield finding("X2", f"{match.name} found ({match.masked}). Revoke it and load it from an "
                                f"environment variable.", file=rel, line=match.line, severity=match.severity)


@check("X3", group=GROUP, title="Environment variables have a .env.example", severity=Severity.WARN,
       rule="CONTRIBUTING.md > Step 7 (placeholder values in .env.example)")
def env_example(ctx: ProjectContext):
    names = {PurePosixPath(rel).name for rel in ctx.files}
    if names & ctx.rules.allowed_names:
        return
    for rel in _scannable(ctx):
        if PurePosixPath(rel).suffix not in _CODE_SUFFIXES:
            continue
        text = ctx.read_text(rel)
        if text and _ENV_USAGE.search(text):
            yield finding("X3", "Code reads environment variables but there is no .env.example; "
                                "copy template/.env.example and list them with placeholder values.", file=rel)
            return


@check("X4", group=GROUP, title="No virtual environments, dependencies or caches", severity=Severity.ERROR,
       rule="CONTRIBUTING.md > Step 8 (no virtual environments tracked)")
def junk_folders(ctx: ProjectContext):
    seen: dict[str, int] = {}
    for rel in ctx.files:
        parts = PurePosixPath(rel.rstrip("/")).parts
        for index, part in enumerate(parts):
            if part in ctx.rules.junk_dirs:
                top = "/".join(parts[: index + 1]) + "/"
                seen[top] = seen.get(top, 0) + 1
                break
    for folder in sorted(seen):
        yield finding("X4", f"'{folder}' would be committed; add it to .gitignore.", file=folder)
