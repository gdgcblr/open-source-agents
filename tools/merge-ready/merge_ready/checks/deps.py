"""Checks for declared dependency manifest consistency (R01)."""

from __future__ import annotations

import ast
import json
import re
import sys
import tomllib
from typing import Any

from merge_ready.model import Finding, RuleResult, Severity, Verdict
from merge_ready.project import ProjectContext

IMPORT_ALIAS_MAP = {
    "google.adk": "google-adk",
    "google.genai": "google-genai",
    "google.generativeai": "google-generativeai",
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "PIL": "pillow",
    "cv2": "opencv-python",
    "bs4": "beautifulsoup4",
    "sklearn": "scikit-learn",
    "fitz": "pymupdf",
    "jwt": "pyjwt",
    "git": "gitpython",
    "psycopg2": "psycopg2-binary",
}

TEST_FRAMEWORKS = {"pytest", "unittest", "mock"}


def normalize_package_name(name: str) -> str:
    """Normalize Python package name per PEP 503 (lowercase, dashes for underscores/dots)."""
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def extract_manifest_dependencies(ctx: ProjectContext) -> set[str]:
    """Parse declared dependencies from available manifests."""
    declared: set[str] = set()

    # 1. requirements.txt
    req_txt = ctx.read_text("requirements.txt")
    if req_txt:
        for line in req_txt.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith("#") or line_str.startswith("-r"):
                continue
            # Strip extras, version specifiers, and environment markers
            pkg = re.split(r"[><=~!;\s\[]", line_str)[0].strip()
            if pkg:
                declared.add(normalize_package_name(pkg))

    # 2. pyproject.toml
    pyproject_txt = ctx.read_text("pyproject.toml")
    if pyproject_txt:
        try:
            data = tomllib.loads(pyproject_txt)
            deps = data.get("project", {}).get("dependencies", [])
            for dep in deps:
                pkg = re.split(r"[><=~!;\s\[]", dep)[0].strip()
                if pkg:
                    declared.add(normalize_package_name(pkg))

            # Poetry fallback
            poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            for pkg in poetry_deps:
                if pkg.lower() != "python":
                    declared.add(normalize_package_name(pkg))
        except Exception:
            pass

    # 3. package.json
    pkg_json = ctx.read_text("package.json")
    if pkg_json:
        try:
            data = json.loads(pkg_json)
            for pkg in data.get("dependencies", {}):
                declared.add(normalize_package_name(pkg))
            for pkg in data.get("devDependencies", {}):
                declared.add(normalize_package_name(pkg))
        except Exception:
            pass

    return declared


def get_local_modules(ctx: ProjectContext) -> set[str]:
    """Identify modules and packages defined directly inside the project."""
    local_names: set[str] = set()
    for rel_path in ctx.files:
        parts = rel_path.parts
        if parts:
            first = parts[0]
            if rel_path.suffix == ".py":
                local_names.add(rel_path.stem)
            if (ctx.project_path / first).is_dir():
                local_names.add(first)
    return local_names


def extract_python_imports(ctx: ProjectContext) -> dict[str, list[tuple[str, int]]]:
    """Extract top-level and dotted external imports from Python source files."""
    imports: dict[str, list[tuple[str, int]]] = {}

    for rel_path in ctx.files:
        if rel_path.suffix != ".py":
            continue
        posix = rel_path.as_posix()
        txt = ctx.read_text(rel_path)
        if not txt:
            continue
        try:
            tree = ast.parse(txt, filename=posix)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.setdefault(alias.name, []).append((posix, node.lineno))
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.setdefault(node.module, []).append((posix, node.lineno))
        except Exception:
            pass

    return imports


def check_r01(ctx: ProjectContext, config: dict[str, Any]) -> RuleResult:
    """R01: Compare external static imports in code against declared manifest dependencies."""
    rule_id = "R01"
    name = "Declared Dependency Manifest"
    source = config.get("source_rule", "CONTRIBUTING.md Step 7 & Quality Standards")

    declared = extract_manifest_dependencies(ctx)
    posix_files = {p.as_posix() for p in ctx.files}
    has_manifest_file = any(m in posix_files for m in ("requirements.txt", "pyproject.toml", "package.json"))

    if not has_manifest_file:
        return RuleResult(
            rule_id=rule_id,
            name=name,
            verdict=Verdict.SKIP,
            reason="No dependency manifest found to compare.",
        )

    stdlib = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else set()
    local_modules = get_local_modules(ctx)
    raw_imports = extract_python_imports(ctx)

    if not raw_imports:
        return RuleResult(
            rule_id=rule_id,
            name=name,
            verdict=Verdict.PASS,
            reason="No external Python imports detected.",
        )

    findings: list[Finding] = []

    for full_import, locations in raw_imports.items():
        top_level = full_import.split(".")[0]

        # Exclude standard library
        if top_level in stdlib:
            continue

        # Exclude local modules
        if top_level in local_modules:
            continue

        # Check if test file import and test framework
        is_all_tests = all("test" in p.lower() for p, _ in locations)
        if is_all_tests and top_level in TEST_FRAMEWORKS:
            continue

        # Resolve package name via alias map or top_level
        canonical_pkg = None
        for alias_prefix, pkg_name in IMPORT_ALIAS_MAP.items():
            if full_import == alias_prefix or full_import.startswith(alias_prefix + "."):
                canonical_pkg = pkg_name
                break

        if not canonical_pkg:
            canonical_pkg = top_level

        norm_pkg = normalize_package_name(canonical_pkg)

        if norm_pkg not in declared:
            primary_path, primary_line = locations[0]
            loc_str = ", ".join(f"{p}:{l}" for p, l in locations[:2])
            findings.append(
                Finding(
                    rule_id=rule_id,
                    severity=Severity.WARNING,
                    message=f"Import '{full_import}' may be missing from dependency manifest (expected '{canonical_pkg}').",
                    path=primary_path,
                    line=primary_line,
                    evidence=f"Imported at {loc_str}, but '{canonical_pkg}' is not declared in requirements.txt or pyproject.toml.",
                    fix=f"Add '{canonical_pkg}' to requirements.txt or pyproject.toml.",
                    source_rule=source,
                )
            )

    if findings:
        return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.WARN, findings=findings)

    return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.PASS)
