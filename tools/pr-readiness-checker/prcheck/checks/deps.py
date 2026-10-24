"""M1-M2: dependency manifests."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import PurePosixPath

from ..context import ProjectContext, SkipCheck
from ..models import Severity
from ..registry import check, finding

GROUP = "dependencies"

_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?\s*(.*)$")
_VERSION_SPEC = re.compile(r"(===|==|~=|!=|<=|>=|<|>|@)")


def _manifests(ctx: ProjectContext) -> list[str]:
    return [rel for rel in ctx.files if PurePosixPath(rel).name in ctx.rules.manifests]


@check("M1", group=GROUP, title="Dependencies are declared in a manifest", severity=Severity.ERROR,
       rule="CONTRIBUTING.md > Step 7; Quality & Security Standards 'Dependency Tracking'")
def has_manifest(ctx: ProjectContext):
    if not _manifests(ctx):
        yield finding("M1", "No dependency manifest found (requirements.txt, pyproject.toml, package.json, go.mod, ...).")


def _unpinned_requirements(text: str) -> list[str]:
    names = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "git+", "http://", "https://", ".")):
            continue
        match = _REQ_NAME.match(line)
        if match and not _VERSION_SPEC.search(match.group(3)):
            names.append(match.group(1))
    return names


def _unpinned_pyproject(text: str) -> list[str]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    project = data.get("project", {})
    specs = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        specs.extend(group)
    return _unpinned_requirements("\n".join(specs))


def _unpinned_package_json(text: str) -> list[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    names = []
    for key in ("dependencies", "devDependencies"):
        for name, version in (data.get(key) or {}).items():
            if str(version).strip() in {"*", "", "latest", "x"}:
                names.append(name)
    return names


@check("M2", group=GROUP, title="Dependency versions are pinned", severity=Severity.INFO,
       rule="CONTRIBUTING.md > Reproducibility")
def pinned_versions(ctx: ProjectContext):
    manifests = _manifests(ctx)
    if not manifests:
        raise SkipCheck("No manifest to inspect (see M1).")
    for rel in manifests:
        name = PurePosixPath(rel).name
        text = ctx.read_text(rel)
        if text is None:
            continue
        if name.startswith("requirements"):
            unpinned = _unpinned_requirements(text)
        elif name == "pyproject.toml":
            unpinned = _unpinned_pyproject(text)
        elif name == "package.json":
            unpinned = _unpinned_package_json(text)
        else:
            continue
        if unpinned:
            yield finding("M2", f"No version given for: {', '.join(unpinned)}. Pinning makes setup reproducible.",
                          file=rel)
