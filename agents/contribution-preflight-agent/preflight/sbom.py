import json
import re
import tomllib
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

TOOL_NAME = "contribution-preflight-agent"
PYPI_SPEC = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$")
PYPI_EXACT = re.compile(r"^==\s*([A-Za-z0-9._+!-]+)$")
NPM_EXACT = re.compile(r"^v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-+]*)?)$")
GO_LINE = re.compile(r"^\s*(?:require\s+)?([\w.\-/~]+)\s+(v[\w.\-+]+)")
LOCK_FILES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml")


def _component(name: str, version: str, ecosystem: str, source: str, spec: str = "", scope: str = "required") -> dict:
    pinned = bool(version)
    return {
        "name": name,
        "version": version,
        "ecosystem": ecosystem,
        "source": source,
        "pinned": pinned,
        "spec": spec or (f"=={version}" if pinned else ""),
        "scope": scope,
        "purl": purl_for(name, version, ecosystem),
    }


def purl_for(name: str, version: str, ecosystem: str) -> str:
    suffix = f"@{quote(version)}" if version else ""
    if ecosystem == "PyPI":
        return f"pkg:pypi/{name.lower().replace('_', '-')}{suffix}"
    if ecosystem == "npm":
        return f"pkg:npm/{quote(name, safe='/')}{suffix}"
    if ecosystem == "Go":
        return f"pkg:golang/{name}{suffix}"
    return f"pkg:generic/{name}{suffix}"


def parse_python_requirement(line: str, source: str) -> dict | None:
    text = line.split("#", 1)[0].split(";", 1)[0].strip()
    if not text or text.startswith("-") or "://" in text or " @ " in text:
        return None
    match = PYPI_SPEC.match(text)
    if not match:
        return None
    name, _, rest = match.groups()
    rest = rest.strip()
    exact = PYPI_EXACT.match(rest)
    if exact:
        return _component(name, exact.group(1), "PyPI", source)
    return _component(name, "", "PyPI", source, spec=rest or "any version")


def parse_requirements_txt(path: Path) -> list[dict]:
    components = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        component = parse_python_requirement(line, path.name)
        if component:
            components.append(component)
    return components


def parse_pyproject(path: Path) -> list[dict]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return []
    entries = data.get("project", {}).get("dependencies", [])
    components = []
    for entry in entries if isinstance(entries, list) else []:
        component = parse_python_requirement(str(entry), path.name)
        if component:
            components.append(component)
    return components


def parse_package_json(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    components = []
    for section, scope in (("dependencies", "required"), ("devDependencies", "optional")):
        table = data.get(section, {})
        for name, spec in (table.items() if isinstance(table, dict) else []):
            exact = NPM_EXACT.match(str(spec).strip())
            components.append(_component(name, exact.group(1) if exact else "", "npm", path.name, spec=str(spec), scope=scope))
    return components


def parse_go_mod(path: Path) -> list[dict]:
    components = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith(("module", "go ", "toolchain", "//", ")", "require (")) or not stripped:
            continue
        match = GO_LINE.match(stripped)
        if match:
            components.append(_component(match.group(1), match.group(2), "Go", path.name))
    return components


PARSERS = (
    ("requirements.txt", parse_requirements_txt),
    ("pyproject.toml", parse_pyproject),
    ("package.json", parse_package_json),
    ("go.mod", parse_go_mod),
)


def has_lockfile(root: Path) -> bool:
    return any((root / name).is_file() for name in LOCK_FILES)


def collect_components(project_path: str) -> list[dict]:
    root = Path(project_path)
    components = []
    seen = set()
    for filename, parser in PARSERS:
        path = root / filename
        if not path.is_file():
            continue
        for component in parser(path):
            key = (component["ecosystem"], component["name"].lower())
            if key not in seen:
                seen.add(key)
                components.append(component)
    return components


def bom_ref(component: dict) -> str:
    return component["purl"] or f"{component['ecosystem']}:{component['name']}"


def build_cyclonedx(project: str, generated: datetime, components: list[dict], vulnerabilities: list[dict]) -> dict:
    bom_components = []
    for component in components:
        entry = {
            "type": "library",
            "bom-ref": bom_ref(component),
            "name": component["name"],
            "purl": component["purl"],
            "scope": component["scope"],
        }
        if component["version"]:
            entry["version"] = component["version"]
        else:
            entry["properties"] = [{"name": "preflight:version-spec", "value": component["spec"]}]
        bom_components.append(entry)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": generated.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tools": {"components": [{"type": "application", "name": TOOL_NAME}]},
            "component": {"type": "application", "name": project, "bom-ref": project},
        },
        "components": bom_components,
        "vulnerabilities": [
            {
                "id": item["id"],
                "source": {"name": "OSV", "url": f"https://osv.dev/vulnerability/{item['id']}"},
                "affects": [{"ref": item["ref"]}],
            }
            for item in vulnerabilities
        ],
    }
