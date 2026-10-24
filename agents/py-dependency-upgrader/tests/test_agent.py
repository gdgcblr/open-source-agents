from __future__ import annotations

import ast
from pathlib import Path

import requests

import agent as agent_module
from agent import (
    _build_failure_feedback,
    _ensure_test_signature_utils_file,
    _resolve_python_executable,
    _select_call_shapes,
    _select_test_symbols,
    assess_changelog_risk,
    choose_safe_upgrade,
    discover_dependency_packages,
    find_safe_upgrade_version,
    generate_package_usage_test,
    get_compatible_release_versions,
    inspect_package_usage,
    load_runtime_settings,
    normalize_python_version,
    validate_candidate_versions,
)


def test_discover_dependency_packages_from_pyproject(tmp_path: Path) -> None:
    project = tmp_path / "pyproject.toml"
    project.write_text(
        """
[project]
dependencies = [
  "requests>=2.31.0",
  "pandas>=2.2.0",
]
""",
        encoding="utf-8",
    )

    packages = discover_dependency_packages(tmp_path)
    names = {record.name for record in packages}

    assert "requests" in names
    assert "pandas" in names


def test_discover_dependency_packages_from_nested_requirements_dir(tmp_path: Path) -> None:
    requirements_dir = tmp_path / "requirements"
    requirements_dir.mkdir()
    (requirements_dir / "base.txt").write_text("requests>=2.31.0\n", encoding="utf-8")
    (requirements_dir / "dev.txt").write_text("-r base.txt\npytest>=8.0\n", encoding="utf-8")

    packages = discover_dependency_packages(tmp_path)
    names = {record.name for record in packages}

    assert "requests" in names
    assert "pytest" in names


def test_find_safe_upgrade_version_uses_pypi_metadata(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    payload = {
        "releases": {
            "2.31.0": [{"requires_python": ">=3.8"}],
            "2.32.0": [{"requires_python": ">=3.9"}],
            "2.32.2": [{"requires_python": ">=3.8"}],
            "3.0.0": [{"requires_python": ">=3.12"}],
        }
    }

    def fake_get(url: str, timeout: int):
        assert url == "https://pypi.org/pypi/requests/json"
        return FakeResponse(payload)

    monkeypatch.setattr(requests, "get", fake_get)
    result = find_safe_upgrade_version("requests", current_version="2.31.0", python_version="3.11")

    assert result["safe_upgrade_version"] == "2.32.2"
    assert result["status"] == "ok"
    assert result["target_python_version"] == "3.11.0"


def test_find_safe_upgrade_version_tracks_python_blockers(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    payload = {
        "releases": {
            "2.3.0": [{"requires_python": ">=3.9"}],
            "3.0.0": [{"requires_python": ">=3.10"}],
        }
    }

    def fake_get(url: str, timeout: int):
        assert url == "https://pypi.org/pypi/pandas/json"
        return FakeResponse(payload)

    monkeypatch.setattr(requests, "get", fake_get)
    result = find_safe_upgrade_version("pandas", current_version="2.2.0", python_version="3.9")

    assert result["safe_upgrade_version"] == "2.3.0"
    assert result["blocked_by_python"][0]["version"] == "3.0.0"


def test_get_compatible_release_versions_skips_patch_releases(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    payload = {
        "releases": {
            "4.1.0": [{"requires_python": ">=3.9"}],
            "4.1.3": [{"requires_python": ">=3.9"}],
            "4.2.0": [{"requires_python": ">=3.9"}],
            "4.2.6": [{"requires_python": ">=3.9"}],
            "5.0.0": [{"requires_python": ">=3.9"}],
            "5.0.1": [{"requires_python": ">=3.9"}],
        }
    }

    def fake_get(url: str, timeout: int):
        assert url == "https://pypi.org/pypi/demo-pkg/json"
        return FakeResponse(payload)

    monkeypatch.setattr(requests, "get", fake_get)
    versions = get_compatible_release_versions(
        "demo-pkg",
        python_version="3.11",
        current_version="4.1.0",
        limit=5,
    )

    assert versions == ["4.2.0", "5.0.0"]


def test_get_compatible_release_versions_skips_current_minor_line(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    payload = {
        "releases": {
            "4.0.0": [{"requires_python": ">=3.9"}],
            "4.0.1": [{"requires_python": ">=3.9"}],
            "4.1.0": [{"requires_python": ">=3.9"}],
            "4.1.2": [{"requires_python": ">=3.9"}],
            "4.2.0": [{"requires_python": ">=3.9"}],
        }
    }

    def fake_get(url: str, timeout: int):
        assert url == "https://pypi.org/pypi/celery/json"
        return FakeResponse(payload)

    monkeypatch.setattr(requests, "get", fake_get)
    versions = get_compatible_release_versions(
        "celery",
        python_version="3.11",
        current_version="4.0.0",
        limit=3,
    )

    assert versions == ["4.1.0", "4.2.0"]


def test_choose_safe_upgrade_only_sets_safe_value_after_validation_pass() -> None:
    metadata = {
        "package": "requests",
        "current_version": "2.31.0",
        "safe_upgrade_version": "2.32.2",
        "latest_available_version": "2.32.2",
        "status": "ok",
        "reason": "test",
    }

    result = choose_safe_upgrade(metadata, [{"version": "2.32.2", "status": "failed", "reason": "pytest failed"}])

    assert result["compatible_upgrade_version"] == "2.32.2"
    assert result["validated_upgrade_version"] is None
    assert result["safe_upgrade_version"] is None
    assert result["status"] == "failed-validation"
    assert "pytest failed" in result["reason"]


def test_choose_safe_upgrade_uses_validated_version_when_tests_pass() -> None:
    metadata = {
        "package": "requests",
        "current_version": "2.31.0",
        "safe_upgrade_version": "2.32.2",
        "latest_available_version": "2.32.2",
        "target_python_version": "3.11.0",
        "blocked_by_python": [{"version": "3.0.0", "requires_python": ">=3.12"}],
        "status": "ok",
        "reason": "test",
    }

    result = choose_safe_upgrade(metadata, [{"version": "2.32.2", "status": "passed", "reason": "success"}])

    assert result["compatible_upgrade_version"] == "2.32.2"
    assert result["validated_upgrade_version"] == "2.32.2"
    assert result["safe_upgrade_version"] == "2.32.2"
    assert result["status"] == "ok"


def test_choose_safe_upgrade_blocks_high_risk_changelog_versions() -> None:
    metadata = {
        "package": "requests",
        "current_version": "2.31.0",
        "safe_upgrade_version": "2.32.2",
        "latest_available_version": "2.32.2",
        "status": "ok",
        "reason": "test",
    }
    validation_results = [
        {
            "version": "2.32.2",
            "status": "passed",
            "reason": "success",
            "changelog_risk": {"level": "high"},
        }
    ]

    result = choose_safe_upgrade(metadata, validation_results)

    assert result["safe_upgrade_version"] is None
    assert result["status"] == "changelog-warning"


def test_ignores_virtualenv_files_when_scanning(tmp_path: Path) -> None:
    venv_dir = tmp_path / ".venv" / "lib" / "python3.11" / "site-packages"
    venv_dir.mkdir(parents=True)
    (venv_dir / "ignored_pkg.py").write_text("import requests\n", encoding="utf-8")

    (tmp_path / "requirements.txt").write_text("requests>=2.31.0\n", encoding="utf-8")

    packages = discover_dependency_packages(tmp_path)
    names = {record.name for record in packages}

    assert "requests" in names
    assert "flask" not in names


def test_inspect_package_usage_detects_actual_repo_calls(tmp_path: Path) -> None:
    app = tmp_path / "service.py"
    app.write_text(
        "import requests\n\nresponse = requests.get('https://example.com')\nfrom requests import Session\n",
        encoding="utf-8",
    )

    usage = inspect_package_usage(tmp_path, "requests")

    assert usage["package"] == "requests"
    assert "requests.get" in usage["files"][0]["usage"] or "get" in usage["symbol_usage"]
    assert "Session" in usage["symbol_usage"]
    assert "requests" not in usage["symbol_usage"]
    assert {"symbol": "get", "positional_count": 1, "keyword_names": []} in usage["call_shapes"]


def test_inspect_package_usage_detects_alias_call_shapes(tmp_path: Path) -> None:
    app = tmp_path / "service.py"
    app.write_text(
        "import requests as rq\n\nrq.get('https://example.com', timeout=3)\n",
        encoding="utf-8",
    )

    usage = inspect_package_usage(tmp_path, "requests")

    assert "get" in usage["symbol_usage"]
    assert {"symbol": "get", "positional_count": 1, "keyword_names": ["timeout"]} in usage["call_shapes"]


def test_select_test_symbols_filters_package_name() -> None:
    usage_info = {"symbol_usage": ["get", "requests", "Session", ""]}  # type: ignore[dict-item]
    symbols = _select_test_symbols("requests", usage_info)

    assert "requests" not in symbols
    assert symbols == ["get", "Session"]


def test_select_call_shapes_filters_by_selected_symbols() -> None:
    usage_info = {
        "symbol_usage": ["get", "Session"],
        "call_shapes": [
            {"symbol": "get", "positional_count": 1, "keyword_names": ["timeout"]},
            {"symbol": "requests", "positional_count": 0, "keyword_names": []},
        ],
    }
    shapes = _select_call_shapes("requests", usage_info)

    assert shapes == [{"symbol": "get", "positional_count": 1, "keyword_names": ["timeout"]}]


def test_normalize_python_version_handles_short_versions() -> None:
    assert normalize_python_version("3.11") == "3.11.0"
    assert normalize_python_version("Python 3.9") == "3.9.0"
    assert normalize_python_version("3.11.5") == "3.11.5"


def test_assess_changelog_risk_detects_high_risk_markers(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload=None, text=""):
            self._payload = payload
            self.text = text

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_get(url: str, timeout: int):
        if url == "https://pypi.org/pypi/requests/2.32.2/json":
            return FakeResponse(
                payload={
                    "info": {
                        "project_urls": {
                            "Changelog": "https://example.com/changelog",
                        }
                    }
                }
            )
        if url == "https://example.com/changelog":
            return FakeResponse(text="Breaking change: migration required before upgrade.")
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(requests, "get", fake_get)
    risk = assess_changelog_risk("requests", "2.32.2")

    assert risk["level"] == "high"
    assert risk["sources"] == ["https://example.com/changelog"]


def test_ensure_test_signature_utils_file_creates_helper_module(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    utils_path = _ensure_test_signature_utils_file(tests_dir)
    content = utils_path.read_text(encoding="utf-8")

    assert utils_path.name == "_dependency_test_utils.py"
    assert "def check_symbol_signature_compatibility(module, symbol_name: str):" in content
    assert (
        "def check_call_shape_compatibility(module, symbol_name: str, positional_count: int, keyword_names: list[str]):"
        in content
    )


def test_generate_package_usage_test_has_valid_python_indentation(tmp_path: Path) -> None:
    app = tmp_path / "service.py"
    app.write_text("import requests\nrequests.get('https://example.com')\n", encoding="utf-8")

    test_path = generate_package_usage_test(tmp_path, "requests", inspect_package_usage(tmp_path, "requests"))
    source = test_path.read_text(encoding="utf-8")

    ast.parse(source)
    assert "from tests._dependency_test_utils import (" in source
    assert "check_call_shape_compatibility" in source
    assert "    assert hasattr(module, 'get')" in source
    assert "        assert hasattr(module, 'get')" not in source
    assert "assert hasattr(module, 'requests')" not in source


def test_load_runtime_settings_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_NAME", "openai/gpt-4.1-mini")
    monkeypatch.setenv("LOG_LEVEL", "debug")

    model_name, log_level = load_runtime_settings()

    assert model_name == "openai/gpt-4.1-mini"
    assert log_level == 10


def test_load_runtime_settings_supports_model_aliases(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_NAME", "")
    monkeypatch.setenv("ADK_MODEL", "anthropic/claude-sonnet-4-6")
    monkeypatch.setenv("LOG_LEVEL", "info")

    model_name, log_level = load_runtime_settings()

    assert model_name == "anthropic/claude-sonnet-4-6"
    assert log_level == 20


def test_build_failure_feedback_includes_actionable_details() -> None:
    details = _build_failure_feedback(
        stage="dependency_install",
        command=["python", "-m", "pip", "install", "pkg==1.0.0"],
        returncode=1,
        stdout="Collecting pkg",
        stderr="No matching distribution found",
    )

    assert details["stage"] == "dependency_install"
    assert details["exit_code"] == 1
    assert "No matching distribution found" in details["ai_feedback"]


def test_resolve_python_executable_prefers_target_runtime(monkeypatch) -> None:
    monkeypatch.setattr(agent_module.sys, "executable", "/usr/bin/python3.14")

    def fake_runtime(executable: str):
        if executable == "/usr/bin/python3.14":
            return "3.14.0"
        if executable == "/opt/python3.11/bin/python3.11":
            return "3.11.9"
        return None

    def fake_which(name: str):
        if name == "python3.11":
            return "/opt/python3.11/bin/python3.11"
        return None

    monkeypatch.setattr(agent_module, "_python_runtime_version", fake_runtime)
    monkeypatch.setattr(agent_module.shutil, "which", fake_which)

    executable, runtime_version, is_target_match = _resolve_python_executable("3.11")

    assert executable == "/opt/python3.11/bin/python3.11"
    assert runtime_version == "3.11.9"
    assert is_target_match is True


def test_validate_candidate_versions_skips_when_target_runtime_unavailable(monkeypatch, tmp_path: Path) -> None:
    app = tmp_path / "service.py"
    app.write_text("import requests\nrequests.get('https://example.com')\n", encoding="utf-8")

    monkeypatch.setattr(
        agent_module,
        "_resolve_python_executable",
        lambda version: ("/usr/bin/python3.14", "3.14.5", False),
    )
    monkeypatch.setattr(
        agent_module,
        "get_compatible_release_versions",
        lambda *args, **kwargs: ["4.1.0", "4.2.0"],
    )
    monkeypatch.setattr(agent_module.shutil, "which", lambda name: None)

    results = validate_candidate_versions(
        "celery",
        tmp_path,
        python_version="3.11",
        current_version="4.0.0",
        limit=3,
    )

    assert len(results) == 1
    assert results[0]["status"] == "skipped"
    assert "Target Python 3.11.0 is not available locally and uv is not installed." in results[0]["reason"]
    assert results[0]["target_python_match"] is False
