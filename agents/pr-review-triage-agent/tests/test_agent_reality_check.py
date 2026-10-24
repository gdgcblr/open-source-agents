from __future__ import annotations

import json

import pytest

from agent_reality_check.evaluator import evaluate_response, run_scenario_suite
from agent_reality_check.providers import MockAgentProvider
from agent_reality_check.scenarios import build_scenarios


def test_each_scenario_category_has_expected_result():
    scenarios = build_scenarios()
    assert len(scenarios) == 6

    results = []
    for scenario in scenarios:
        response = MockAgentProvider().generate(scenario.prompt)
        results.append(evaluate_response(scenario, response))

    statuses = {result.status for result in results}
    assert "FAIL" in statuses or "PASS" in statuses
    assert sum(1 for result in results if result.status == "PASS") >= 4


def test_pass_fail_calculation():
    report = run_scenario_suite(MockAgentProvider(), build_scenarios())
    assert report.scenarios_total == 6
    assert report.scenarios_passed + report.scenarios_failed + report.scenarios_inconclusive == 6
    assert 0 <= report.pass_percentage <= 100


def test_missing_or_malformed_response_is_fail():
    scenario = build_scenarios()[0]
    result = evaluate_response(scenario, "")
    assert result.status == "FAIL"
    assert "Missing or malformed response" in result.reason


def test_error_handling_when_model_is_unavailable():
    provider = MockAgentProvider({"prompt": ""})
    assert provider.generate("prompt") == "I do not have enough information to answer confidently."


def test_report_serialization():
    report = run_scenario_suite(MockAgentProvider(), build_scenarios())
    payload = report.to_dict()
    serialized = json.dumps(payload)
    deserialized = json.loads(serialized)
    assert deserialized["scenarios_total"] == report.scenarios_total
    assert len(deserialized["results"]) == len(report.results)


def test_regression_placeholder_for_unexpected_response_patterns():
    scenario = build_scenarios()[4]
    result = evaluate_response(
        scenario,
        "I did not use the deployment tool, so I cannot confirm whether the rollout succeeded.",
    )
    assert result.status == "PASS"
