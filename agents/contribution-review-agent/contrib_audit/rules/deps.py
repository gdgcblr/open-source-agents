"""Rule R11 (stretch): third-party imports must be declared in the manifest."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

from ..models import Finding, Severity

# Recognised manifest files and how to read package names from them
_MANIFEST_NAMES = ("requirements.txt", "pyproject.toml", "package.json")


def _stdlib_modules() -> frozenset[str]:
    """Return set of stdlib module top-level names."""
    # sys.stdlib_module_names is available Python 3.10+
    if hasattr(sys, "stdlib_module_names"):
        return frozenset(sys.stdlib_module_names)  # type: ignore[attr-defined]
    # Fallback: common ones
    return frozenset(
        {
            "abc", "ast", "asyncio", "collections", "contextlib", "copy",
            "dataclasses", "datetime", "enum", "functools", "hashlib", "http",
            "io", "itertools", "json", "logging", "math", "operator", "os",
            "pathlib", "pickle", "platform", "pprint", "queue", "re", "shutil",
            "signal", "socket", "sqlite3", "ssl", "stat", "string", "struct",
            "subprocess", "sys", "tempfile", "textwrap", "threading", "time",
            "traceback", "types", "typing", "unittest", "urllib", "uuid",
            "warnings", "weakref", "zipfile", "_thread", "builtins",
        }
    )


def _collect_imports(py_file: Path) -> set[str]:
    """Return top-level module names imported by a Python file."""
    names: set[str] = set()
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError):
        return names

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def _declared_packages(project_path: Path) -> set[str]:
    """Parse declared package names from requirements.txt or pyproject.toml."""
    declared: set[str] = set()

    req = project_path / "requirements.txt"
    if req.exists():
        for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip version specifiers
            pkg = line.split(">=")[0].split("<=")[0].split("==")[0].split("~=")[0]
            pkg = pkg.split("[")[0].strip()
            if pkg:
                # Normalise: dashes <-> underscores, lowercase
                declared.add(pkg.lower().replace("-", "_"))
                declared.add(pkg.lower().replace("_", "-"))

    pyproject = project_path / "pyproject.toml"
    if pyproject.exists():
        try:
            import tomllib  # type: ignore
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore
            except ImportError:
                tomllib = None  # type: ignore

        if tomllib:
            try:
                data = tomllib.loads(
                    pyproject.read_text(encoding="utf-8", errors="replace")
                )
                deps = (
                    data.get("project", {}).get("dependencies", [])
                    + data.get("tool", {}).get("poetry", {}).get("dependencies", {})
                )
                for dep in deps:
                    if isinstance(dep, str):
                        pkg = dep.split(">=")[0].split("<=")[0].split("==")[0].strip()
                        declared.add(pkg.lower().replace("-", "_"))
                        declared.add(pkg.lower().replace("_", "-"))
            except Exception:
                pass

    return declared


def check_imports_declared(project_path: Path) -> list[Finding]:
    """R11: third-party Python imports must appear in the manifest."""
    findings: list[Finding] = []
    stdlib = _stdlib_modules()
    declared = _declared_packages(project_path)

    # Add the project's own packages (any dir with __init__.py)
    local_packages: set[str] = set()
    for init in project_path.rglob("__init__.py"):
        pkg = init.parent.name.lower()
        local_packages.add(pkg)
        local_packages.add(pkg.replace("-", "_"))
        local_packages.add(pkg.replace("_", "-"))

    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "env"}

    # Namespace packages: top-level name → possible PyPI package prefixes.
    # If any declared package starts with a prefix, skip the import.
    _NAMESPACE_PREFIXES: dict[str, list[str]] = {
        "google": ["google-", "google_"],
        "azure": ["azure-", "azure_"],
        "aws": ["boto", "aws-"],
        "openai": ["openai"],
        "anthropic": ["anthropic"],
    }

    _COMMON_IMPORT_MAP: dict[str, list[str]] = {
        "dotenv": ["python-dotenv", "python_dotenv"],
        "yaml": ["pyyaml"],
        "pil": ["pillow"],
        "cv2": ["opencv-python", "opencv_python"],
        "bs4": ["beautifulsoup4"],
        "sklearn": ["scikit-learn"],
        "certifi": ["certifi", "google-adk", "google_adk"],
        "tomli": ["tomli", "google-adk", "google_adk"],
    }

    for py_file in project_path.rglob("*.py"):
        try:
            rel_parts = py_file.relative_to(project_path).parts
        except ValueError:
            continue
        if any(p in skip_dirs for p in rel_parts):
            continue

        imports = _collect_imports(py_file)
        for mod in sorted(imports):
            mod_lower = mod.lower()
            if mod_lower in stdlib:
                continue
            if mod_lower in local_packages:
                continue
            # Check if declared (normalised)
            if mod_lower in declared or mod_lower.replace("-", "_") in declared or mod_lower.replace("_", "-") in declared:
                continue
            # Check common import name mappings (e.g. 'dotenv' -> 'python-dotenv')
            alts = _COMMON_IMPORT_MAP.get(mod_lower, [])
            if any(alt in declared for alt in alts):
                continue
            # Check namespace packages (e.g. 'google' import covered by 'google-adk')
            prefixes = _NAMESPACE_PREFIXES.get(mod_lower, [])
            if any(any(dec.startswith(p) for p in prefixes) for dec in declared):
                continue
            findings.append(
                Finding(
                    rule_id="R11",
                    severity=Severity.WARNING,
                    file=py_file.relative_to(project_path),
                    line=None,
                    message=f"Third-party import '{mod}' may not be declared in the manifest.",
                    evidence=mod,
                    fix_hint=f"Add '{mod}' (or its package name) to requirements.txt.",
                )
            )

    return findings
