"""Lockfile and manifest parsers that build a small SBOM."""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Callable
from pathlib import PurePosixPath

from rce_sentinel.models import Dependency

REQ_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._\-]*)(?:\[[^\]]*\])?\s*==\s*([^\s;#]+)")
REQ_LOOSE_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._\-]*)")
YARN_HEAD_RE = re.compile(r'^"?(@?[^@\s"]+)@')
YARN_VER_RE = re.compile(r'^\s+version\s+"?([^"\s]+)"?')


def normalize_pypi(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirements(text: str, path: str) -> list[Dependency]:
    deps = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "git+", "http")):
            continue
        if m := REQ_RE.match(line):
            deps.append(Dependency(ecosystem="PyPI", name=normalize_pypi(m.group(1)),
                                   version=m.group(2), file=path))
        elif m := REQ_LOOSE_RE.match(line):
            deps.append(Dependency(ecosystem="PyPI", name=normalize_pypi(m.group(1)),
                                   version=None, file=path))
    return deps


def parse_toml_lock(text: str, path: str, ecosystem: str) -> list[Dependency]:
    data = tomllib.loads(text)
    out = []
    for pkg in data.get("package", []):
        name = pkg.get("name", "")
        if ecosystem == "PyPI":
            name = normalize_pypi(name)
        out.append(Dependency(ecosystem=ecosystem, name=name, version=pkg.get("version"),
                              file=path))
    return out


def parse_pipfile_lock(text: str, path: str) -> list[Dependency]:
    data = json.loads(text)
    out = []
    for section in ("default", "develop"):
        for name, meta in data.get(section, {}).items():
            ver = str(meta.get("version", "")).lstrip("=") or None
            out.append(Dependency(ecosystem="PyPI", name=normalize_pypi(name), version=ver,
                                  file=path))
    return out


def parse_package_lock(text: str, path: str) -> list[Dependency]:
    data = json.loads(text)
    out: dict[tuple[str, str], Dependency] = {}
    for key, meta in (data.get("packages") or {}).items():
        if not key:
            continue
        name = meta.get("name") or key.split("node_modules/")[-1]
        if ver := meta.get("version"):
            out[(name, ver)] = Dependency(ecosystem="npm", name=name, version=ver, file=path)
    for name, meta in (data.get("dependencies") or {}).items():
        if ver := meta.get("version"):
            out.setdefault((name, ver),
                           Dependency(ecosystem="npm", name=name, version=ver, file=path))
    return list(out.values())


def parse_yarn_lock(text: str, path: str) -> list[Dependency]:
    out = []
    current: str | None = None
    for line in text.splitlines():
        if line and not line.startswith((" ", "#")):
            m = YARN_HEAD_RE.match(line)
            current = m.group(1) if m else None
        elif current and (m := YARN_VER_RE.match(line)):
            out.append(Dependency(ecosystem="npm", name=current, version=m.group(1), file=path))
            current = None
    return out


def parse_go_sum(text: str, path: str) -> list[Dependency]:
    seen: dict[tuple[str, str], Dependency] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        ver = parts[1].removesuffix("/go.mod")
        seen[(parts[0], ver)] = Dependency(ecosystem="Go", name=parts[0], version=ver, file=path)
    return list(seen.values())


Parser = Callable[[str, str], list[Dependency]]

PARSERS: dict[str, Parser] = {
    "poetry.lock": lambda t, p: parse_toml_lock(t, p, "PyPI"),
    "uv.lock": lambda t, p: parse_toml_lock(t, p, "PyPI"),
    "Pipfile.lock": parse_pipfile_lock,
    "package-lock.json": parse_package_lock,
    "npm-shrinkwrap.json": parse_package_lock,
    "yarn.lock": parse_yarn_lock,
    "go.sum": parse_go_sum,
    "Cargo.lock": lambda t, p: parse_toml_lock(t, p, "crates.io"),
}


def parser_for(path: str) -> Parser | None:
    name = PurePosixPath(path).name
    if name in PARSERS:
        return PARSERS[name]
    if re.fullmatch(r"(requirements|constraints)[\w\-.]*\.(txt|in)", name):
        return parse_requirements
    return None


def is_manifest(path: str) -> bool:
    return parser_for(path) is not None


def parse_manifest(path: str, text: str) -> list[Dependency]:
    parser = parser_for(path)
    if parser is None:
        return []
    try:
        return parser(text, path)
    except (ValueError, KeyError, tomllib.TOMLDecodeError):
        return []


def diff_deps(old: list[Dependency], new: list[Dependency]) -> list[Dependency]:
    """Dependencies added or version-changed between two manifest snapshots."""
    before = {(d.ecosystem, d.name, d.version) for d in old}
    return [d for d in new if (d.ecosystem, d.name, d.version) not in before]
