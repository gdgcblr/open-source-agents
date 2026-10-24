"""Parse dependency manifests into a flat list of declared packages."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass

from judge.workspace import Workspace

REQ_LINE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*([^;#]*)")
PEP508 = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$")


@dataclass(frozen=True)
class Dep:
    name: str
    spec: str  # version specifier as written ("" when unpinned)
    ecosystem: str  # "PyPI" | "npm"
    file: str
    line: int | None = None

    @property
    def exact_version(self) -> str | None:
        m = (
            re.fullmatch(r"\s*===?\s*([A-Za-z0-9.+!-]+)\s*", self.spec)
            if self.ecosystem == "PyPI"
            else re.fullmatch(r"\s*v?(\d+\.\d+\.\d+[A-Za-z0-9.+-]*)\s*", self.spec)
        )
        return m.group(1) if m else None

    @property
    def pinned(self) -> bool:
        s = self.spec.strip()
        return bool(s) and s not in ("*", "latest")


@dataclass
class Manifests:
    files: list[str]
    deps: list[Dep]
    errors: list[str]

    @property
    def python_names(self) -> set[str]:
        from judge.analyzers.pyast import normalize_dist

        return {normalize_dist(d.name) for d in self.deps if d.ecosystem == "PyPI"}

    @property
    def npm_names(self) -> set[str]:
        return {d.name for d in self.deps if d.ecosystem == "npm"}


def _requirements(ws: Workspace, rel: str, out: Manifests) -> None:
    for i, line in enumerate((ws.read(rel) or "").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith(("#", "-", "git+", "http")):
            continue
        m = REQ_LINE.match(s)
        if m:
            out.deps.append(Dep(m.group(1), m.group(3).strip(), "PyPI", rel, i))


def _pyproject(ws: Workspace, rel: str, out: Manifests) -> None:
    try:
        data = tomllib.loads(ws.read(rel) or "")
    except tomllib.TOMLDecodeError as exc:
        out.errors.append(f"{rel}: {exc}")
        return
    project = data.get("project", {})
    specs = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        specs.extend(extra)
    for group in data.get("dependency-groups", {}).values():
        specs.extend(s for s in group if isinstance(s, str))
    for s in specs:
        m = PEP508.match(s.split(";")[0])
        if m:
            out.deps.append(Dep(m.group(1), m.group(3).strip(), "PyPI", rel))
    poetry = data.get("tool", {}).get("poetry", {})
    for section in ("dependencies", "dev-dependencies"):
        for name, spec in poetry.get(section, {}).items():
            if name.lower() != "python":
                out.deps.append(Dep(name, spec if isinstance(spec, str) else str(spec.get("version", "")), "PyPI", rel))


def _package_json(ws: Workspace, rel: str, out: Manifests) -> None:
    try:
        data = json.loads(ws.read(rel) or "{}")
    except json.JSONDecodeError as exc:
        out.errors.append(f"{rel}: {exc}")
        return
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        for name, spec in (data.get(section) or {}).items():
            out.deps.append(Dep(name, str(spec).lstrip("^~"), "npm", rel))


def _pipfile(ws: Workspace, rel: str, out: Manifests) -> None:
    try:
        data = tomllib.loads(ws.read(rel) or "")
    except tomllib.TOMLDecodeError as exc:
        out.errors.append(f"{rel}: {exc}")
        return
    for section in ("packages", "dev-packages"):
        for name, spec in data.get(section, {}).items():
            out.deps.append(Dep(name, spec if isinstance(spec, str) and spec != "*" else "", "PyPI", rel))


def _environment_yml(ws: Workspace, rel: str, out: Manifests) -> None:
    in_pip = False
    for i, line in enumerate((ws.read(rel) or "").splitlines(), 1):
        s = line.strip()
        if s.startswith("- pip:"):
            in_pip = True
            continue
        if in_pip and s.startswith("- "):
            m = REQ_LINE.match(s[2:])
            if m:
                out.deps.append(Dep(m.group(1), m.group(3).strip(), "PyPI", rel, i))


PARSERS = {
    "requirements.txt": _requirements,
    "requirements-dev.txt": _requirements,
    "pyproject.toml": _pyproject,
    "package.json": _package_json,
    "pipfile": _pipfile,
    "environment.yml": _environment_yml,
}
OTHER_MANIFESTS = {"go.mod", "cargo.toml", "setup.py", "pom.xml", "build.gradle", "gemfile"}


def parse(ws: Workspace) -> Manifests:
    """Parse every manifest in the workspace once; the result is memoised on the workspace."""
    cached = getattr(ws, "_manifests", None)
    if cached is not None:
        return cached
    out = Manifests(files=[], deps=[], errors=[])
    for rel in ws.files:
        if "node_modules/" in rel:
            continue
        name = rel.rsplit("/", 1)[-1].lower()
        if name in PARSERS or (name.startswith("requirements") and name.endswith(".txt")):
            out.files.append(rel)
            PARSERS.get(name, _requirements)(ws, rel, out)
        elif name in OTHER_MANIFESTS:
            out.files.append(rel)
    ws._manifests = out  # type: ignore[attr-defined]
    return out
