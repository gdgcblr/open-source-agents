"""Executable architecture rules: dependencies may only point inward."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# layer -> import prefixes it must NOT use
RULES = {
    "triage/models.py": ["google", "triage.adapters", "triage.service", "triage.privacy", "ci_triage_agent", "cli"],
    "triage/ports.py": ["google", "triage.adapters", "triage.service", "ci_triage_agent", "cli"],
    "triage/rules.py": ["google", "triage.adapters", "triage.service", "triage.privacy", "ci_triage_agent", "cli", "os", "requests", "httpx"],
    "triage/privacy": ["google", "triage.adapters", "triage.service", "ci_triage_agent", "cli"],
    "triage/service.py": ["google", "defusedxml", "triage.adapters", "ci_triage_agent", "cli"],
    "triage/adapters": ["ci_triage_agent", "cli", "triage.service"],
}


def imports(path: Path) -> set[str]:
    found = set()
    base = ".".join(path.relative_to(ROOT).with_suffix("").parts[:-1])
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # resolve relative imports against the package
                parts = base.split(".")[: len(base.split(".")) - (node.level - 1)]
                found.add(".".join(parts + ([node.module] if node.module else [])))
            elif node.module:
                found.add(node.module)
    return found


def files_for(spec: str):
    p = ROOT / spec
    return [p] if p.is_file() else sorted(p.rglob("*.py"))


def test_dependencies_point_inward():
    violations = []
    for spec, forbidden in RULES.items():
        for f in files_for(spec):
            for imp in imports(f):
                for bad in forbidden:
                    if imp == bad or imp.startswith(bad + "."):
                        violations.append(f"{f.relative_to(ROOT)} must not import {imp}")
    assert not violations, "\n".join(violations)


def test_only_adapters_and_interfaces_touch_google():
    allowed = {"triage/adapters/providers.py", "ci_triage_agent/agent.py", "ci_triage_agent/guardrails.py"}
    offenders = []
    for f in list((ROOT / "triage").rglob("*.py")) + list((ROOT / "ci_triage_agent").rglob("*.py")):
        rel = str(f.relative_to(ROOT))
        if any(i == "google" or i.startswith("google.") for i in imports(f)) and rel not in allowed:
            offenders.append(rel)
    assert not offenders, offenders
