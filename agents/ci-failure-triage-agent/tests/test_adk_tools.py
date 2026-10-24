import os

import pytest

from ci_triage_agent import tools


@pytest.fixture(autouse=True)
def _root(monkeypatch):
    monkeypatch.setenv("TRIAGE_ROOT", os.getcwd())


def test_rules_tool_flaky_sample():
    r = tools.classify_with_rules("samples/flaky/junit.xml", "samples/flaky/ci.log")
    assert r["failures"][0]["rule_verdict"]["category"] == "FLAKY"


def test_unknown_sample_returns_null_verdict():
    r = tools.classify_with_rules("samples/unknown/junit.xml")
    assert r["failures"][0]["rule_verdict"] is None


def test_path_traversal_rejected():
    assert "error" in tools.classify_with_rules("../../etc/passwd")
    assert "error" in tools.get_log_context("/etc/hostname", "x")


def test_log_context_is_redacted():
    r = tools.get_log_context("samples/infra/ci.log", "Could not resolve host", width=5)
    blob = " ".join(r["lines"])
    assert "10.0.3.17" not in blob and "dev@example.com" not in blob and "fake-demo-token" not in blob


def test_agent_definition_loads():
    from ci_triage_agent.agent import root_agent

    assert root_agent.name == "ci_triage_agent" and len(root_agent.tools) == 3
