"""
Integration tests for NutriLoop Multi-Agent Orchestrator.
Tests end-to-end workflow, traces, and benchmark scenario execution.
"""

import pytest
from nutriloop.orchestrator import NutriLoopOrchestrator
from nutriloop.models import UserProfile, DietType
from nutriloop.evaluation.benchmark import BENCHMARK_SCENARIOS
from nutriloop.evaluation.baselines import NutriLoopSystemWrapper


def test_orchestrator_initial_plan():
    orch = NutriLoopOrchestrator()
    profile = UserProfile(diet_type=DietType.VEGETARIAN, daily_calorie_target=1800.0)
    result = orch.run_initial_plan(profile)

    assert result.success
    assert result.verification.is_valid
    assert len(result.traces) > 0
    assert result.original_plan.total_calories > 1000.0


def test_orchestrator_adapt_workflow():
    orch = NutriLoopOrchestrator()
    profile = UserProfile(diet_type=DietType.VEGETARIAN, daily_calorie_target=1800.0)
    initial_res = orch.run_initial_plan(profile)

    adapt_res = orch.adapt_to_disruptions(
        profile=profile,
        current_plan=initial_res.original_plan,
        raw_food_logs=[{"text": "1 plate vegetable poha", "meal_type": "breakfast"}],
        disruptions=[]
    )

    assert adapt_res.success
    assert adapt_res.verification.is_valid
    assert adapt_res.revised_plan.total_calories > 1000.0


def test_all_benchmark_scenarios_pass():
    system = NutriLoopSystemWrapper()
    for scenario in BENCHMARK_SCENARIOS:
        res = system.run(scenario)
        assert res["arithmetic_error_pct"] <= 1.0, f"Failed on {scenario.id}"
        assert len(res["violations"]) == 0, f"Violations on {scenario.id}: {res['violations']}"
