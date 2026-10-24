import pytest

from cicd_failure_investigator.analyzer import analyze_ci_log


def test_detects_dependency_failure():
    result = analyze_ci_log(
        "ERROR: No matching distribution found for example-package==99.0"
    )
    assert result["primary_category"] == "dependency_installation"
    assert result["status"] == "failure_detected"


def test_detects_test_failure():
    result = analyze_ci_log("FAILED tests/test_login.py::test_login")
    assert result["primary_category"] == "test_failure"


def test_detects_authentication_failure():
    result = analyze_ci_log("401 Unauthorized: invalid credentials")
    assert result["primary_category"] == "authentication"


def test_detects_configuration_failure():
    result = analyze_ci_log("FileNotFoundError: config.yaml")
    assert result["primary_category"] == "configuration"


def test_detects_deployment_failure():
    result = analyze_ci_log("DEPLOYMENT_FAILED: deployment failed")
    assert result["primary_category"] == "deployment"


def test_unknown_pattern_is_reported():
    result = analyze_ci_log("Pipeline stopped for an unknown reason")
    assert result["status"] == "no_known_failure_pattern"
    assert result["primary_category"] == "unknown"


@pytest.mark.parametrize("log_text", ["", "   ", "\n"])
def test_empty_log_is_rejected(log_text):
    result = analyze_ci_log(log_text)
    assert result["status"] == "error"
    assert result["evidence"] == []