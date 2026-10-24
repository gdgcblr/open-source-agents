from __future__ import annotations

import ast
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".tox",
    ".ruff_cache",
    "site-packages",
}


def _is_ignored_path(path: Path) -> bool:
    return any(str(part).lower() in {name.lower() for name in IGNORED_DIRS} for part in path.parts)


@dataclass
class DependencyRecord:
    name: str
    version_specifier: str
    source: str
    manifest_path: str
    current_version: str | None = None


def _normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _read_requirement_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _parse_requirement_entry(line: str) -> tuple[str, str] | None:
    cleaned = line.strip()
    if not cleaned or cleaned.startswith("#"):
        return None
    if cleaned.startswith(("-r ", "--requirement")):
        return None
    if cleaned.startswith(("-e ", "--editable")):
        return None
    if cleaned.startswith("--"):
        return None
    if ";" in cleaned:
        cleaned = cleaned.split(";", 1)[0].strip()
    match = re.match(r"^([A-Za-z0-9_.\-]+(?:\[[^\]]+\])?)\s*(.*)$", cleaned)
    if not match:
        return None
    package_name = match.group(1).split("[", 1)[0]
    specifier = match.group(2).strip()
    return package_name, specifier


def _resolve_requirement_include(root: Path, include_path: str, base_file: Path) -> Path | None:
    candidate = (base_file.parent / include_path).resolve()
    if candidate.exists():
        return candidate
    candidate = (root / include_path).resolve()
    if candidate.exists():
        return candidate
    return None


def _collect_requirement_file(path: Path, root: Path, seen: set[Path] | None = None) -> list[DependencyRecord]:
    if seen is None:
        seen = set()
    resolved = path.resolve()
    if resolved in seen:
        return []
    seen.add(resolved)

    results: list[DependencyRecord] = []
    for line in _read_requirement_lines(path):
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        if cleaned.startswith(("-r ", "--requirement")):
            include_name = cleaned.split(None, 1)[1].strip()
            include_path = _resolve_requirement_include(root, include_name, path)
            if include_path is not None:
                results.extend(_collect_requirement_file(include_path, root, seen))
            continue
        parsed = _parse_requirement_entry(line)
        if not parsed:
            continue
        package_name, specifier = parsed
        current_version = _extract_version_hint(specifier)
        results.append(
            DependencyRecord(
                name=_normalize_package_name(package_name),
                version_specifier=specifier,
                source=f"requirements:{path.name}",
                manifest_path=str(path),
                current_version=current_version,
            )
        )
    return results


def _collect_from_requirements(root: Path) -> list[DependencyRecord]:
    results: list[DependencyRecord] = []
    manifests: set[Path] = set()

    for path in root.rglob("*.txt"):
        if _is_ignored_path(path):
            continue
        if not (
            path.name.startswith("requirements") or path.parent.name == "requirements" or "requirements" in path.parts
        ):
            continue
        manifests.add(path.resolve())

    for manifest in sorted(manifests):
        results.extend(_collect_requirement_file(Path(manifest), root, set()))
    return results


def _extract_version_hint(specifier: str) -> str | None:
    if not specifier:
        return None
    for op in ("==", ">=", "<=", "~=", "!=", "~=", "=="):
        if op in specifier:
            pieces = re.split(r"\s*[,\s]+\s*", specifier)
            for piece in pieces:
                if op in piece:
                    value = piece.split(op, 1)[1]
                    if value:
                        return value.strip()
    return None


def _collect_from_pyproject(root: Path) -> list[DependencyRecord]:
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.exists():
        return []

    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover
        return []

    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []

    records: list[DependencyRecord] = []
    project = data.get("project", {})
    for entry in project.get("dependencies", []) or []:
        parsed = _parse_requirement_entry(entry)
        if not parsed:
            continue
        package_name, specifier = parsed
        records.append(
            DependencyRecord(
                name=_normalize_package_name(package_name),
                version_specifier=specifier,
                source="pyproject",
                manifest_path=str(pyproject_path),
                current_version=_extract_version_hint(specifier),
            )
        )

    for group_name, entries in (project.get("optional-dependencies") or {}).items():
        for entry in entries:
            parsed = _parse_requirement_entry(entry)
            if not parsed:
                continue
            package_name, specifier = parsed
            records.append(
                DependencyRecord(
                    name=_normalize_package_name(package_name),
                    version_specifier=specifier,
                    source=f"pyproject[{group_name}]",
                    manifest_path=str(pyproject_path),
                    current_version=_extract_version_hint(specifier),
                )
            )

    dependency_groups = data.get("dependency-groups", {})
    for group_name, entries in dependency_groups.items():
        for entry in entries:
            parsed = _parse_requirement_entry(str(entry))
            if not parsed:
                continue
            package_name, specifier = parsed
            records.append(
                DependencyRecord(
                    name=_normalize_package_name(package_name),
                    version_specifier=specifier,
                    source=f"dependency-groups[{group_name}]",
                    manifest_path=str(pyproject_path),
                    current_version=_extract_version_hint(specifier),
                )
            )

    return records


def _safe_request_json(url: str) -> dict[str, Any]:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.json()


def _safe_request_text(url: str) -> str | None:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    if len(response.text) > 250_000:
        return response.text[:250_000]
    return response.text


def _tail_text(value: str | None, limit: int = 1200) -> str:
    if not value:
        return ""
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[-limit:]


def _build_failure_feedback(
    stage: str, command: list[str], returncode: int, stdout: str, stderr: str
) -> dict[str, Any]:
    stdout_tail = _tail_text(stdout)
    stderr_tail = _tail_text(stderr)
    summary_parts = [f"{stage} failed (exit code {returncode})."]
    if stderr_tail:
        summary_parts.append(f"stderr: {stderr_tail}")
    if stdout_tail:
        summary_parts.append(f"stdout: {stdout_tail}")

    return {
        "stage": stage,
        "command": " ".join(command),
        "exit_code": returncode,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "ai_feedback": " ".join(summary_parts),
    }


def _python_runtime_version(executable: str) -> str | None:
    try:
        result = subprocess.run(
            [
                executable,
                "-c",
                "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}')",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _resolve_python_executable(python_version: str | None) -> tuple[str, str | None, bool]:
    normalized = normalize_python_version(python_version)
    if not normalized:
        return sys.executable, _python_runtime_version(sys.executable), True

    target_parts = normalized.split(".")
    target_major_minor = ".".join(target_parts[:2]) if len(target_parts) >= 2 else normalized

    sys_runtime = _python_runtime_version(sys.executable)
    if sys_runtime and sys_runtime.startswith(f"{target_major_minor}."):
        return sys.executable, sys_runtime, True

    candidates = [f"python{target_major_minor}", f"python{target_parts[0]}", "python3", "python"]
    for candidate in candidates:
        executable = shutil.which(candidate)
        if not executable:
            continue
        runtime = _python_runtime_version(executable)
        if runtime and runtime.startswith(f"{target_major_minor}."):
            return executable, runtime, True

    return sys.executable, sys_runtime, False


def _summarize_validation_failures(validation_results: list[dict[str, Any]]) -> str:
    failed_items = [item for item in validation_results if item.get("status") != "passed"]
    if not failed_items:
        return "No failures were recorded."
    snippets: list[str] = []
    for item in failed_items[:3]:
        version = item.get("version", "unknown")
        details = item.get("failure_details") or {}
        ai_feedback = details.get("ai_feedback") if isinstance(details, dict) else None
        fallback_reason = item.get("reason", "unknown failure")
        snippets.append(f"{version}: {ai_feedback or fallback_reason}")
    if len(failed_items) > 3:
        snippets.append(f"... and {len(failed_items) - 3} more failure(s).")
    return " | ".join(snippets)


def _extract_changelog_urls(metadata_payload: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    info = metadata_payload.get("info", {})
    project_urls = info.get("project_urls", {}) or {}
    preferred_keys = ("changelog", "changes", "release", "history", "news", "what's new", "whats new")

    for key, value in project_urls.items():
        if not isinstance(value, str):
            continue
        key_text = str(key).lower()
        if any(marker in key_text for marker in preferred_keys):
            urls.append(value)

    for fallback_key in ("home_page", "project_url", "package_url"):
        fallback_value = info.get(fallback_key)
        if isinstance(fallback_value, str):
            urls.append(fallback_value)

    unique_urls: list[str] = []
    seen: set[str] = set()
    for url in urls:
        normalized = url.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_urls.append(normalized)
    return unique_urls[:4]


def assess_changelog_risk(package_name: str, version: str) -> dict[str, Any]:
    normalized_name = _normalize_package_name(package_name)
    try:
        payload = _safe_request_json(f"https://pypi.org/pypi/{normalized_name}/{version}/json")
    except requests.RequestException as exc:
        return {
            "level": "unknown",
            "summary": f"Unable to fetch changelog metadata: {exc}",
            "signals": [],
            "sources": [],
        }

    urls = _extract_changelog_urls(payload)
    if not urls:
        return {
            "level": "unknown",
            "summary": "No changelog or release-note URL found in package metadata.",
            "signals": [],
            "sources": [],
        }

    risk_patterns = {
        "high": ("breaking change", "backward incompatible", "removed", "migration required"),
        "medium": ("deprecated", "deprecation", "behavior change", "warning"),
        "low": ("fix", "improvement", "performance"),
    }

    found_signals: list[str] = []
    matched_sources: list[str] = []
    highest_level = "low"
    ranking = {"low": 1, "medium": 2, "high": 3}

    for url in urls:
        try:
            body = _safe_request_text(url)
        except requests.RequestException:
            continue
        if not body:
            continue
        text = body.lower()
        local_hits: list[str] = []
        local_level = "low"
        for level, markers in risk_patterns.items():
            for marker in markers:
                if marker in text:
                    local_hits.append(marker)
                    if ranking[level] > ranking[local_level]:
                        local_level = level
        if local_hits:
            matched_sources.append(url)
            for hit in local_hits[:6]:
                found_signals.append(f"{local_level}:{hit}")
            if ranking[local_level] > ranking[highest_level]:
                highest_level = local_level

    if not matched_sources:
        return {
            "level": "unknown",
            "summary": "Changelog URL(s) found but no known risk markers matched.",
            "signals": [],
            "sources": urls,
        }

    return {
        "level": highest_level,
        "summary": f"Detected {highest_level} changelog risk markers for {normalized_name}=={version}.",
        "signals": found_signals,
        "sources": matched_sources,
    }


def _parse_version(value: str | None) -> Version | None:
    if not value:
        return None
    try:
        return Version(value)
    except InvalidVersion:
        return None


def normalize_python_version(version: str | None) -> str | None:
    if version is None:
        return None
    cleaned = version.strip().strip('"').strip("'")
    if not cleaned:
        return None
    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", cleaned)
    if match:
        cleaned = match.group(1)
    if cleaned.count(".") == 0:
        return f"{cleaned}.0"
    if len(cleaned.split(".")) == 2:
        return f"{cleaned}.0"
    return cleaned


def find_safe_upgrade_version(
    package_name: str, current_version: str | None = None, python_version: str | None = None
) -> dict[str, Any]:
    normalized_name = _normalize_package_name(package_name)
    python_version = normalize_python_version(python_version) or ".".join(str(part) for part in sys.version_info[:3])

    try:
        payload = _safe_request_json(f"https://pypi.org/pypi/{normalized_name}/json")
    except requests.RequestException as exc:  # pragma: no cover - network issue;
        return {
            "package": normalized_name,
            "current_version": current_version,
            "safe_upgrade_version": current_version,
            "latest_available_version": None,
            "target_python_version": python_version,
            "blocked_by_python": [],
            "status": "unavailable",
            "reason": f"Unable to query PyPI: {exc}",
        }

    releases = payload.get("releases", {})
    available_versions: list[Version] = []
    for release_key in releases:
        version = _parse_version(release_key)
        if version is None or version.is_prerelease:
            continue
        available_versions.append(version)

    if not available_versions:
        return {
            "package": normalized_name,
            "current_version": current_version,
            "safe_upgrade_version": current_version,
            "latest_available_version": None,
            "target_python_version": python_version,
            "blocked_by_python": [],
            "status": "no-releases",
            "reason": "No stable releases were found on PyPI.",
        }

    latest_release = max(available_versions)
    current_version_obj = _parse_version(current_version)
    compatible_versions = []
    blocked_by_python: list[dict[str, str]] = []
    release_keys = []
    for release_key in releases:
        parsed = _parse_version(release_key)
        if parsed is not None:
            release_keys.append((parsed, release_key))
    for release_version, release_key in sorted(release_keys, key=lambda item: item[0], reverse=True):
        if current_version_obj is not None and release_version < current_version_obj:
            continue
        release_info = releases.get(release_key, [])
        requires_python = None
        for artifact in release_info:
            requires_python = artifact.get("requires_python") or requires_python
        if requires_python:
            try:
                if not SpecifierSet(requires_python).contains(python_version, prereleases=True):
                    blocked_by_python.append({"version": str(release_version), "requires_python": requires_python})
                    continue
            except InvalidSpecifier:
                pass
        if release_version.is_prerelease:
            continue
        compatible_versions.append(release_version)

    if not compatible_versions:
        return {
            "package": normalized_name,
            "current_version": current_version,
            "safe_upgrade_version": current_version,
            "latest_available_version": str(latest_release),
            "target_python_version": python_version,
            "blocked_by_python": blocked_by_python[:5],
            "status": "no-compatible-release",
            "reason": "No PyPI release is compatible with the current Python version.",
        }

    candidate = max(compatible_versions)
    if current_version_obj is not None and candidate <= current_version_obj:
        safe_upgrade = current_version
    else:
        safe_upgrade = str(candidate)

    return {
        "package": normalized_name,
        "current_version": current_version,
        "safe_upgrade_version": safe_upgrade,
        "latest_available_version": str(latest_release),
        "target_python_version": python_version,
        "blocked_by_python": blocked_by_python[:5],
        "status": "ok",
        "reason": "Highest stable release compatible with the repository Python version.",
    }


def discover_dependency_packages(root: Path) -> list[DependencyRecord]:
    records: list[DependencyRecord] = []
    seen: set[str] = set()
    for collector in (_collect_from_pyproject, _collect_from_requirements):
        for record in collector(root):
            key = record.name
            if key not in seen:
                seen.add(key)
                records.append(record)
    return sorted(records, key=lambda item: item.name)


def inspect_package_usage(root: Path, package_name: str) -> dict[str, Any]:
    normalized_name = _normalize_package_name(package_name)
    files: list[dict[str, Any]] = []
    symbols: set[str] = set()
    call_shape_keys: set[tuple[str, int, tuple[str, ...]]] = set()

    for path in root.rglob("*.py"):
        if _is_ignored_path(path):
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue

        usage_patterns: list[str] = []
        package_aliases: set[str] = set()
        direct_symbol_aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_name = _normalize_package_name(alias.name)
                    if imported_name == normalized_name or imported_name.startswith(f"{normalized_name}."):
                        usage_patterns.append(f"import {alias.name}")
                        local_alias = alias.asname or alias.name.split(".", 1)[0]
                        package_aliases.add(local_alias)
            elif isinstance(node, ast.ImportFrom):
                module_name = (node.module or "").split(".", 1)[0]
                if _normalize_package_name(module_name) == normalized_name:
                    used_symbols = [alias.name for alias in node.names]
                    usage_patterns.append(f"from {node.module} import {', '.join(used_symbols)}")
                    for alias in node.names:
                        if alias.name == "*":
                            continue
                        symbols.add(alias.name)
                        direct_symbol_aliases[alias.asname or alias.name] = alias.name
            elif isinstance(node, ast.Call):
                func = node.func
                resolved_symbol: str | None = None
                usage_pattern: str | None = None
                if isinstance(func, ast.Name):
                    if func.id in direct_symbol_aliases:
                        resolved_symbol = direct_symbol_aliases[func.id]
                        usage_pattern = resolved_symbol
                elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    if func.value.id in package_aliases or _normalize_package_name(func.value.id) == normalized_name:
                        resolved_symbol = func.attr
                        usage_pattern = f"{func.value.id}.{func.attr}"
                elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Attribute):
                    value = func.value
                    if isinstance(value.value, ast.Name) and (
                        value.value.id in package_aliases or _normalize_package_name(value.value.id) == normalized_name
                    ):
                        resolved_symbol = func.attr
                        usage_pattern = f"{value.value.id}.{value.attr}.{func.attr}"

                if resolved_symbol:
                    symbols.add(resolved_symbol)
                    if usage_pattern:
                        usage_patterns.append(usage_pattern)
                    keyword_names = tuple(sorted({kw.arg for kw in node.keywords if isinstance(kw.arg, str)}))
                    call_shape_keys.add((resolved_symbol, len(node.args), keyword_names))

        if usage_patterns:
            files.append(
                {
                    "path": str(path.relative_to(root)),
                    "usage": usage_patterns[:10],
                }
            )

    return {
        "package": normalized_name,
        "symbol_usage": sorted(symbols),
        "call_shapes": [
            {"symbol": symbol, "positional_count": positional_count, "keyword_names": list(keyword_names)}
            for symbol, positional_count, keyword_names in sorted(call_shape_keys)
        ],
        "files": files,
    }


def _select_test_symbols(package_name: str, usage_info: dict[str, Any]) -> list[str]:
    normalized_name = _normalize_package_name(package_name)
    symbols = usage_info.get("symbol_usage", [])
    selected: list[str] = []
    for symbol in symbols:
        if not isinstance(symbol, str):
            continue
        cleaned = symbol.strip()
        if not cleaned or not cleaned.isidentifier():
            continue
        if _normalize_package_name(cleaned) == normalized_name:
            continue
        selected.append(cleaned)
    return selected


def _select_call_shapes(package_name: str, usage_info: dict[str, Any]) -> list[dict[str, Any]]:
    selected_symbols = set(_select_test_symbols(package_name, usage_info))
    raw_shapes = usage_info.get("call_shapes", [])
    selected_shapes: list[dict[str, Any]] = []
    for shape in raw_shapes:
        if not isinstance(shape, dict):
            continue
        symbol = shape.get("symbol")
        positional_count = shape.get("positional_count")
        keyword_names = shape.get("keyword_names", [])
        if not isinstance(symbol, str) or symbol not in selected_symbols:
            continue
        if not isinstance(positional_count, int) or positional_count < 0:
            continue
        if not isinstance(keyword_names, list):
            continue
        cleaned_keyword_names = [name for name in keyword_names if isinstance(name, str) and name.isidentifier()]
        selected_shapes.append(
            {
                "symbol": symbol,
                "positional_count": positional_count,
                "keyword_names": cleaned_keyword_names,
            }
        )
    return selected_shapes[:20]


def _ensure_test_signature_utils_file(tests_dir: Path) -> Path:
    utils_path = tests_dir / "_dependency_test_utils.py"
    content = '''"""Shared helpers for generated dependency usage tests."""

import inspect


def check_symbol_signature_compatibility(module, symbol_name: str):
    try:
        symbol = getattr(module, symbol_name)
    except AttributeError:
        return False, f"{symbol_name} is missing from the package API."

    if not callable(symbol):
        return True, None

    try:
        signature = inspect.signature(symbol)
    except (TypeError, ValueError, RecursionError):
        return True, None

    params = [
        param for param in signature.parameters.values()
        if param.name not in {"self", "cls"}
        and param.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]
    if not params:
        return True, None

    required = [param for param in params if param.default is inspect.Parameter.empty]
    if required:
        names = {param.name.lower() for param in required}
        if not names:
            return False, f"{symbol_name} has a callable signature that cannot be validated."
    return True, None


def check_call_shape_compatibility(module, symbol_name: str, positional_count: int, keyword_names: list[str]):
    try:
        symbol = getattr(module, symbol_name)
    except AttributeError:
        return False, f"{symbol_name} is missing from the package API."

    if not callable(symbol):
        return False, f"{symbol_name} exists but is not callable."

    try:
        signature = inspect.signature(symbol)
    except (TypeError, ValueError, RecursionError):
        return True, None

    args = [object() for _ in range(max(0, positional_count))]
    kwargs = {name: object() for name in keyword_names if isinstance(name, str) and name.isidentifier()}
    try:
        signature.bind_partial(*args, **kwargs)
    except TypeError as exc:
        return False, f"{symbol_name} call shape mismatch: {exc}"
    return True, None
'''
    utils_path.write_text(content, encoding="utf-8")
    return utils_path


def generate_test_file_for_packages(repo_root: Path, package_names: list[str]) -> Path:
    tests_dir = repo_root / "tests"
    tests_dir.mkdir(exist_ok=True)
    test_path = tests_dir / "test_generated_dependency_smoke.py"

    package_list = "\n".join(f'    "{name}",' for name in package_names)
    content = f'''"""Auto-generated smoke tests for third-party Python dependencies."""

import pytest

PACKAGE_NAMES = [
{package_list}
]


@pytest.mark.parametrize("package_name", PACKAGE_NAMES)
def test_dependency_can_import(package_name: str):
    module = pytest.importorskip(package_name)
    assert module is not None


@pytest.mark.parametrize("package_name", PACKAGE_NAMES)
def test_dependency_has_version_metadata(package_name: str):
    module = pytest.importorskip(package_name)
    version = getattr(module, "__version__", None)
    assert version is not None or hasattr(module, "__spec__")
'''
    test_path.write_text(content, encoding="utf-8")
    return test_path


def generate_package_usage_test(repo_root: Path, package_name: str, usage_info: dict[str, Any] | None = None) -> Path:
    tests_dir = repo_root / "tests"
    tests_dir.mkdir(exist_ok=True)
    _ensure_test_signature_utils_file(tests_dir)
    safe_name = re.sub(r"[^a-zA-Z0-9_]+", "_", _normalize_package_name(package_name)).strip("_") or "dependency"
    test_path = tests_dir / f"test_{safe_name}_usage.py"

    usage_info = usage_info or inspect_package_usage(repo_root, package_name)
    symbols = _select_test_symbols(package_name, usage_info)
    call_shapes = _select_call_shapes(package_name, usage_info)
    import_lines = []
    if symbols:
        for symbol in symbols[:8]:
            import_lines.append(f"assert hasattr(module, {symbol!r})")
            import_lines.append(f"ok, message = check_symbol_signature_compatibility(module, {symbol!r})")
            import_lines.append("assert ok, message")
    else:
        import_lines.append("assert module is not None")

    for shape in call_shapes[:12]:
        import_lines.append(
            "ok, message = check_call_shape_compatibility("
            f"module, {shape['symbol']!r}, positional_count={shape['positional_count']}, "
            f"keyword_names={shape['keyword_names']!r})"
        )
        import_lines.append("assert ok, message")

    content = f'''"""Usage-based tests for {package_name}."""

import pytest
from tests._dependency_test_utils import (
    check_call_shape_compatibility,
    check_symbol_signature_compatibility,
)


def test_{safe_name}_imports_and_exposes_expected_api():
    module = pytest.importorskip({package_name!r})
    assert module is not None
{chr(10).join("    " + line for line in import_lines)}
'''
    test_path.write_text(content, encoding="utf-8")
    return test_path


def get_compatible_release_versions(
    package_name: str,
    python_version: str | None = None,
    limit: int = 5,
    current_version: str | None = None,
    skip_patch_releases: bool = True,
) -> list[str]:
    normalized_name = _normalize_package_name(package_name)
    python_version = normalize_python_version(python_version) or ".".join(str(part) for part in sys.version_info[:3])
    current_obj = _parse_version(current_version)
    try:
        payload = _safe_request_json(f"https://pypi.org/pypi/{normalized_name}/json")
    except requests.RequestException:
        return []

    compatible_versions: list[Version] = []
    for release_key in sorted(
        payload.get("releases", {}).keys(), key=lambda item: Version(item) if item else Version("0")
    ):
        parsed = _parse_version(release_key)
        if parsed is None or parsed.is_prerelease:
            continue
        if current_obj is not None and parsed <= current_obj:
            continue
        release_info = payload.get("releases", {}).get(release_key, [])
        requires_python = None
        for artifact in release_info:
            requires_python = artifact.get("requires_python") or requires_python
        if requires_python:
            try:
                if not SpecifierSet(requires_python).contains(python_version, prereleases=True):
                    continue
            except InvalidSpecifier:
                pass
        compatible_versions.append(parsed)

    if not compatible_versions:
        return []

    if current_obj is None:
        ordered_desc = sorted(compatible_versions, reverse=True)
        if not skip_patch_releases:
            return [str(version) for version in ordered_desc[:limit]]
        selected_desc: list[Version] = []
        seen_steps: set[tuple[int, int]] = set()
        for version in ordered_desc:
            step = (version.major, version.minor)
            if step in seen_steps:
                continue
            seen_steps.add(step)
            selected_desc.append(version)
            if len(selected_desc) >= limit:
                break
        return [str(version) for version in selected_desc]

    ordered_versions = sorted(compatible_versions)
    if not skip_patch_releases:
        return [str(version) for version in ordered_versions[:limit]]

    selected_versions: list[Version] = []
    seen_steps: set[tuple[int, int]] = set()
    current_step = (current_obj.major, current_obj.minor) if current_obj is not None else None
    for version in ordered_versions:
        step = (version.major, version.minor)
        if current_step is not None and step == current_step:
            continue
        if step in seen_steps:
            continue
        seen_steps.add(step)
        selected_versions.append(version)
        if len(selected_versions) >= limit:
            break
    return [str(version) for version in selected_versions]


def validate_candidate_versions(
    package_name: str,
    repo_root: Path,
    python_version: str | None = None,
    limit: int = 3,
    current_version: str | None = None,
) -> list[dict[str, Any]]:
    normalized_name = _normalize_package_name(package_name)
    requested_python_version = normalize_python_version(python_version)
    requested_major_minor = (
        requested_python_version.rsplit(".", 1)[0]
        if requested_python_version and "." in requested_python_version
        else requested_python_version
    )
    usage_info = inspect_package_usage(repo_root, normalized_name)
    test_path = generate_package_usage_test(repo_root, normalized_name, usage_info)
    uv_executable = shutil.which("uv")
    base_python_executable, runtime_python_version, target_runtime_match = _resolve_python_executable(python_version)
    versions = get_compatible_release_versions(
        normalized_name,
        python_version,
        limit=limit,
        current_version=current_version,
    )
    results: list[dict[str, Any]] = []

    if requested_python_version and not uv_executable and not target_runtime_match:
        fallback_version = versions[0] if versions else current_version or "unknown"
        return [
            {
                "version": fallback_version,
                "status": "skipped",
                "reason": (
                    f"Target Python {requested_python_version} is not available locally and uv is not installed. "
                    f"Validation would run on Python {runtime_python_version or 'unknown'}, so version checks were skipped."
                ),
                "failure_details": {
                    "stage": "runtime_resolution",
                    "command": f"python{requested_python_version.rsplit('.', 1)[0]}",
                    "exit_code": 0,
                    "stdout_tail": "",
                    "stderr_tail": "",
                    "ai_feedback": ("Install uv and rerun, or install matching Python interpreter and rerun."),
                },
                "changelog_risk": {},
                "sequence_halted": True,
                "validation_python": runtime_python_version,
                "target_python_match": False,
            }
        ]

    for version in versions:
        changelog_risk = assess_changelog_risk(normalized_name, version)
        with tempfile.TemporaryDirectory(prefix=f"{normalized_name}-") as tmp_dir:
            venv_dir = Path(tmp_dir) / "venv"
            if requested_major_minor and uv_executable:
                venv_create_cmd = [uv_executable, "venv", "--python", requested_major_minor, str(venv_dir)]
            else:
                venv_create_cmd = [base_python_executable, "-m", "venv", str(venv_dir)]
            venv_create_result = subprocess.run(venv_create_cmd, check=False, capture_output=True, text=True)
            if not venv_dir.exists():
                details = _build_failure_feedback(
                    stage="venv_create",
                    command=venv_create_cmd,
                    returncode=venv_create_result.returncode,
                    stdout=venv_create_result.stdout,
                    stderr=venv_create_result.stderr,
                )
                results.append(
                    {
                        "version": version,
                        "status": "skipped",
                        "reason": details["ai_feedback"],
                        "failure_details": details,
                        "changelog_risk": changelog_risk,
                        "sequence_halted": True,
                        "validation_python": runtime_python_version,
                        "target_python_match": target_runtime_match,
                    }
                )
                break
            py_executable = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            runtime_python_version = _python_runtime_version(str(py_executable)) or runtime_python_version
            target_runtime_match = (
                runtime_python_version.startswith(f"{requested_major_minor}.")
                if requested_major_minor and runtime_python_version
                else target_runtime_match
            )
            if uv_executable:
                install_cmd = [
                    uv_executable,
                    "pip",
                    "install",
                    "--python",
                    str(py_executable),
                    "--quiet",
                    "pytest",
                    f"{normalized_name}=={version}",
                ]
            else:
                install_cmd = [
                    str(py_executable),
                    "-m",
                    "pip",
                    "install",
                    "--quiet",
                    "pytest",
                    f"{normalized_name}=={version}",
                ]
            install_result = subprocess.run(install_cmd, capture_output=True, text=True)
            if install_result.returncode != 0:
                details = _build_failure_feedback(
                    stage="dependency_install",
                    command=install_cmd,
                    returncode=install_result.returncode,
                    stdout=install_result.stdout,
                    stderr=install_result.stderr,
                )
                if not target_runtime_match:
                    details["ai_feedback"] += (
                        f" Validation runtime Python is {runtime_python_version or 'unknown'} while target requested"
                        f" {normalize_python_version(python_version) or 'unspecified'}."
                    )
                results.append(
                    {
                        "version": version,
                        "status": "failed",
                        "reason": details["ai_feedback"],
                        "failure_details": details,
                        "changelog_risk": changelog_risk,
                        "sequence_halted": True,
                        "validation_python": runtime_python_version,
                        "target_python_match": target_runtime_match,
                    }
                )
                break

            signature_probe = f"""
import inspect
import importlib
module = importlib.import_module({normalized_name!r})
for name in {sorted(_select_test_symbols(normalized_name, usage_info))!r}:
    try:
        obj = getattr(module, name)
    except AttributeError:
        raise AssertionError(f'{{name}} is missing from the package API')
    if callable(obj):
        try:
            inspect.signature(obj)
        except (TypeError, ValueError, RecursionError):
            continue
"""
            probe_path = Path(tmp_dir) / "signature_probe.py"
            probe_path.write_text(signature_probe, encoding="utf-8")
            probe_result = subprocess.run(
                [str(py_executable), str(probe_path)],
                capture_output=True,
                text=True,
                cwd=str(repo_root),
            )
            if probe_result.returncode != 0:
                details = _build_failure_feedback(
                    stage="signature_probe",
                    command=[str(py_executable), str(probe_path)],
                    returncode=probe_result.returncode,
                    stdout=probe_result.stdout,
                    stderr=probe_result.stderr,
                )
                results.append(
                    {
                        "version": version,
                        "status": "failed",
                        "reason": details["ai_feedback"],
                        "failure_details": details,
                        "changelog_risk": changelog_risk,
                        "sequence_halted": True,
                        "validation_python": runtime_python_version,
                        "target_python_match": target_runtime_match,
                    }
                )
                break
            test_result = subprocess.run(
                [str(py_executable), "-m", "pytest", "-q", str(test_path)],
                capture_output=True,
                text=True,
                cwd=str(repo_root),
            )
            results.append(
                {
                    "version": version,
                    "status": "passed" if test_result.returncode == 0 else "failed",
                    "reason": (
                        test_result.stdout.strip() or test_result.stderr.strip() or "pytest checks passed"
                        if test_result.returncode == 0
                        else _build_failure_feedback(
                            stage="usage_test_execution",
                            command=[str(py_executable), "-m", "pytest", "-q", str(test_path)],
                            returncode=test_result.returncode,
                            stdout=test_result.stdout,
                            stderr=test_result.stderr,
                        )["ai_feedback"]
                    ),
                    "failure_details": (
                        None
                        if test_result.returncode == 0
                        else _build_failure_feedback(
                            stage="usage_test_execution",
                            command=[str(py_executable), "-m", "pytest", "-q", str(test_path)],
                            returncode=test_result.returncode,
                            stdout=test_result.stdout,
                            stderr=test_result.stderr,
                        )
                    ),
                    "changelog_risk": changelog_risk,
                    "sequence_halted": test_result.returncode != 0,
                    "validation_python": runtime_python_version,
                    "target_python_match": target_runtime_match,
                }
            )
            if test_result.returncode != 0:
                break
    return results


def choose_safe_upgrade(metadata_result: dict[str, Any], validation_results: list[dict[str, Any]]) -> dict[str, Any]:
    compatible_version = metadata_result.get("safe_upgrade_version")
    package_name = metadata_result.get("package")
    current_version = metadata_result.get("current_version")
    latest_available = metadata_result.get("latest_available_version")

    if metadata_result.get("status") not in {"ok", "no-compatible-release", "no-releases", "unavailable"}:
        result = {
            "package": package_name,
            "current_version": current_version,
            "metadata_candidate_version": compatible_version,
            "tested_upgrade_version": None,
            "recommended_upgrade_version": None,
            "compatible_upgrade_version": compatible_version,
            "validated_upgrade_version": None,
            "safe_upgrade_version": None,
            "latest_available_version": latest_available,
            "status": metadata_result.get("status", "unknown"),
            "reason": metadata_result.get("reason", "Dependency upgrade recommendation not validated."),
        }
        return result

    passed_candidates = []
    for item in validation_results:
        if item.get("status") != "passed":
            continue
        risk_level = (item.get("changelog_risk") or {}).get("level", "unknown")
        if risk_level == "high":
            continue
        passed_candidates.append(item)

    passed_versions = [item.get("version") for item in passed_candidates if item.get("version")]
    if passed_versions:
        highest_passed = max(passed_versions, key=lambda value: _parse_version(value) or Version("0"))
        current_obj = _parse_version(current_version)
        highest_obj = _parse_version(highest_passed)
        safe_version = (
            current_version
            if current_obj is not None and highest_obj is not None and highest_obj <= current_obj
            else highest_passed
        )
        result = {
            "package": package_name,
            "current_version": current_version,
            "metadata_candidate_version": compatible_version,
            "tested_upgrade_version": safe_version,
            "recommended_upgrade_version": safe_version,
            "compatible_upgrade_version": compatible_version,
            "validated_upgrade_version": safe_version,
            "safe_upgrade_version": safe_version,
            "latest_available_version": latest_available,
            "status": "ok",
            "reason": "Highest version that passed repo-specific validation tests, Python compatibility checks, and changelog risk screening.",
        }
        return result

    if validation_results:
        high_risk_passed = [
            item.get("version")
            for item in validation_results
            if item.get("status") == "passed" and (item.get("changelog_risk") or {}).get("level") == "high"
        ]
        if high_risk_passed:
            result = {
                "package": package_name,
                "current_version": current_version,
                "metadata_candidate_version": compatible_version,
                "tested_upgrade_version": None,
                "recommended_upgrade_version": None,
                "compatible_upgrade_version": compatible_version,
                "validated_upgrade_version": None,
                "safe_upgrade_version": None,
                "latest_available_version": latest_available,
                "status": "changelog-warning",
                "reason": f"Candidate versions passed tests but changelog flagged high-risk markers: {', '.join(high_risk_passed)}.",
            }
            return result
        failure_summary = _summarize_validation_failures(validation_results)
        result = {
            "package": package_name,
            "current_version": current_version,
            "metadata_candidate_version": compatible_version,
            "tested_upgrade_version": None,
            "recommended_upgrade_version": None,
            "compatible_upgrade_version": compatible_version,
            "validated_upgrade_version": None,
            "safe_upgrade_version": None,
            "latest_available_version": latest_available,
            "status": "failed-validation",
            "reason": f"No candidate version passed validation. Details: {failure_summary}",
        }
        return result

    result = {
        "package": package_name,
        "current_version": current_version,
        "metadata_candidate_version": compatible_version,
        "tested_upgrade_version": None,
        "recommended_upgrade_version": None,
        "compatible_upgrade_version": compatible_version,
        "validated_upgrade_version": None,
        "safe_upgrade_version": None,
        "latest_available_version": latest_available,
        "status": metadata_result.get("status", "unknown"),
        "reason": metadata_result.get("reason", "Validation was not executed."),
    }
    return result


def analyze_repository(
    project_path: str | Path,
    package_limit: int | None = None,
    python_version: str | None = None,
    selected_packages: str | list[str] | None = None,
) -> dict[str, Any]:
    root = Path(project_path).resolve()
    target_python_version = normalize_python_version(python_version) or ".".join(
        str(part) for part in sys.version_info[:3]
    )
    print(f"[1/4] Scanning repository: {root}")

    discovered = discover_dependency_packages(root)
    if selected_packages:
        package_names = [
            item.strip().lower()
            for item in (
                selected_packages if isinstance(selected_packages, list) else str(selected_packages).split(",")
            )
            if item.strip()
        ]
        dependencies = [record for record in discovered if record.name.lower() in package_names]
        print(
            f"[2/4] Filtered to {len(dependencies)} selected package(s): {', '.join(record.name for record in dependencies)}"
        )
    else:
        dependencies = discovered
        if package_limit is not None:
            dependencies = dependencies[:package_limit]
            print(f"[2/4] Limited dependency candidates to first {len(dependencies)} packages for testing")
        else:
            print(f"[2/4] Discovered {len(dependencies)} dependency candidates")

    package_names = [record.name for record in dependencies]
    print("[3/4] Generating smoke test file for discovered packages")
    test_file = generate_test_file_for_packages(root, package_names)
    package_usage_details = []
    validation_details = []

    print(f"[4/4] Checking safe upgrade versions against Python {target_python_version}")
    recommendations = []
    for index, record in enumerate(dependencies, start=1):
        print(f"  -> {index}/{len(dependencies)}: checking {record.name}")
        usage_info = inspect_package_usage(root, record.name)
        package_usage_details.append({"package": record.name, "usage": usage_info})
        generated_usage_test = generate_package_usage_test(root, record.name, usage_info)
        validation_results = validate_candidate_versions(
            record.name,
            root,
            target_python_version,
            limit=3,
            current_version=record.current_version,
        )
        validation_details.append(
            {"package": record.name, "test_file": str(generated_usage_test), "versions": validation_results}
        )
        metadata_result = find_safe_upgrade_version(record.name, record.current_version, target_python_version)
        validated_result = choose_safe_upgrade(metadata_result, validation_results)
        recommendations.append(
            {
                "package": validated_result["package"],
                "current_version": validated_result["current_version"],
                "metadata_candidate_version": validated_result.get("metadata_candidate_version"),
                "tested_upgrade_version": validated_result.get("tested_upgrade_version"),
                "recommended_upgrade_version": validated_result.get("recommended_upgrade_version"),
                "compatible_upgrade_version": validated_result.get("compatible_upgrade_version"),
                "validated_upgrade_version": validated_result.get("validated_upgrade_version"),
                "safe_upgrade_version": validated_result.get("safe_upgrade_version"),
                "status": validated_result["status"],
                "reason": validated_result["reason"],
                "usage_analysis": usage_info,
                "version_checks": validation_results,
            }
        )

    print(f"Completed dependency analysis for {len(dependencies)} package(s).")
    return {
        "project_root": str(root),
        "target_python_version": target_python_version,
        "package_count": len(dependencies),
        "packages": [
            {"name": record.name, "version_specifier": record.version_specifier, "source": record.source}
            for record in dependencies
        ],
        "generated_test_file": str(test_file),
        "package_usage": package_usage_details,
        "version_validation": validation_details,
        "safe_upgrade_report": recommendations,
    }


def analyze_repository_tool(project_path: str) -> dict[str, Any]:
    return analyze_repository(project_path)


def recommend_upgrades_for_package(package_name: str, current_version: str | None = None) -> dict[str, Any]:
    return find_safe_upgrade_version(package_name, current_version)


def load_runtime_settings() -> tuple[str, int]:
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    model_name = ""
    for key in ("MODEL_NAME", "ADK_MODEL", "LLM_MODEL"):
        value = os.getenv(key)
        if value and value.strip():
            model_name = value.strip()
            break
    if not model_name:
        model_name = "gemini-2.5-flash"
    log_level_name = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    log_level = getattr(logging, log_level_name, logging.INFO)
    logging.basicConfig(level=log_level, format="%(levelname)s:%(name)s:%(message)s")
    return model_name, log_level


def build_agent() -> LlmAgent:
    model_name, _ = load_runtime_settings()
    return LlmAgent(
        name="python_dependency_upgrader",
        model=model_name,
        description="Analyzes Python dependencies, creates smoke tests, and recommends safe upgrade versions.",
        instruction=(
            "You inspect a repository for Python dependencies, generate sensible pytest smoke tests, "
            "and recommend the highest version each dependency can safely upgrade to given the project Python version."
        ),
        tools=[
            FunctionTool(analyze_repository_tool),
            FunctionTool(recommend_upgrades_for_package),
        ],
    )


root_agent = build_agent()


if __name__ == "__main__":
    result = analyze_repository(project_path=".")
    print(json.dumps(result, indent=2))
