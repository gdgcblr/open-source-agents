"""The core must stay framework-agnostic: only adapters may import agent/MCP/LLM libraries."""

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "murphy"
CORE = ["core", "config", "checks", "report", "plugins.py", "secrets.py", "replay.py"]
FORBIDDEN = ("google.adk", "fastmcp", "litellm", "mcp", "examples")


def imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def files(entries):
    for entry in entries:
        p = PKG / entry
        yield from ([p] if p.is_file() else p.rglob("*.py"))


def test_core_has_no_framework_imports():
    offenders = {}
    for f in files(CORE):
        bad = [n for n in imports(f) if n.split(".")[0] in {x.split(".")[0] for x in FORBIDDEN} and
               any(n == x or n.startswith(x + ".") for x in FORBIDDEN)]
        if bad:
            offenders[str(f.relative_to(PKG))] = bad
    assert offenders == {}


def test_only_adk_adapter_imports_adk():
    users = [str(f.relative_to(PKG)) for f in PKG.rglob("*.py") if any(n.startswith("google.adk") for n in imports(f))]
    assert users == ["targets/adk.py"]


def test_nothing_in_package_imports_examples():
    assert [f for f in PKG.rglob("*.py") if any(n.startswith("examples") for n in imports(f))] == []
