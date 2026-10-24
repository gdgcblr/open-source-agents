"""
Unit and integration tests for Google GenAI / ADK integration and safety guardrails in NutriLoop AI.
"""

import pytest
from unittest.mock import MagicMock, patch
from nutriloop.models import (
    UserProfile,
    DietType,
    HealthGoal,
    DisruptionEvent,
    Meal,
    DailyMealPlan
)
from nutriloop.agents.base import BaseAgent
from nutriloop.agents.food_analyzer import FoodAnalyzerAgent
from nutriloop.agents.adaptive_replanner import AdaptiveReplannerAgent
from nutriloop.agents.verifier import IndependentVerificationEngine
from nutriloop.nutrition_engine import create_meal_item


def test_gemini_client_initialization_offline():
    """Verify that in offline mode (no API key), agents safely report no live LLM and don't crash."""
    agent = BaseAgent(name="TestAgent", role="Tester")
    agent.api_key = None
    assert not agent.has_live_gemini()
    assert agent.get_gemini_client() is None


def test_food_analyzer_fallback_and_guardrails():
    """Verify FoodAnalyzer parses food and grounds all values strictly in ICMR-NIN IFCT tables."""
    analyzer = FoodAnalyzerAgent()
    entry = analyzer.analyze_food_log(
        text="1 fried vegetable samosa and 1 cutting masala chai",
        meal_type="snack",
        is_unplanned=True
    )
    assert len(entry.consumed_items) == 2
    item_names = [i.name.lower() for i in entry.consumed_items]
    assert any("samosa" in n for n in item_names)
    assert any("chai" in n for n in item_names)
    # Ensure calories are mathematically derived and > 0
    assert entry.total_calories > 300.0


def test_anti_starvation_guardrail_intercepts_low_calories():
    """Verify that dinner calorie floor guardrail prevents punitive starvation (< 250 kcal)."""
    verifier = IndependentVerificationEngine()
    profile = UserProfile(
        name="Test User",
        diet_type=DietType.VEGETARIAN,
        daily_calorie_target=1800.0,
        daily_budget_inr=200.0
    )

    # Construct an artificially punitively starved dinner (only 1 roti = 90 kcal)
    starved_dinner = Meal(
        meal_type="dinner",
        items=[create_meal_item("roti_whole_wheat", 30.0, "1 roti")]
    )
    plan = DailyMealPlan(
        plan_id="starved_plan",
        meals=[
            Meal(meal_type="breakfast", items=[create_meal_item("poha_vegetable", 180.0)]),
            Meal(meal_type="lunch", items=[create_meal_item("dal_moong_tadka", 150.0)]),
            starved_dinner
        ]
    )

    audit = verifier.verify_plan(plan, profile)
    # Must flag the anti-starvation violation
    assert not audit.is_valid
    assert any("anti-starvation" in v.lower() or "starvation" in v.lower() for v in audit.constraint_violations)


def test_dietary_guardrails_jain_and_vegan():
    """Verify that strict religious/lifestyle restrictions are audited with 0 tolerance."""
    verifier = IndependentVerificationEngine()

    # Jain user receiving food with root vegetables
    jain_profile = UserProfile(
        name="Jain User",
        diet_type=DietType.JAIN,
        daily_calorie_target=1800.0,
        daily_budget_inr=200.0
    )
    non_jain_plan = DailyMealPlan(
        plan_id="bad_jain_plan",
        meals=[
            Meal(
                meal_type="dinner",
                items=[create_meal_item("palak_paneer", 150.0)]  # Contains onion/garlic
            )
        ]
    )
    audit = verifier.verify_plan(non_jain_plan, jain_profile)
    assert not audit.is_valid
    assert any("jain" in v.lower() for v in audit.constraint_violations)
