"""
Unit tests for Independent Verification Engine.
Tests constraint checks, allergen detection, and arithmetic integrity validation.
"""

import pytest
from nutriloop.agents.verifier import IndependentVerificationEngine
from nutriloop.models import (
    DailyMealPlan,
    Meal,
    UserProfile,
    DietType
)
from nutriloop.nutrition_engine import create_meal_item


@pytest.fixture
def verifier():
    return IndependentVerificationEngine()


def test_verifier_flags_diet_violation(verifier):
    profile = UserProfile(diet_type=DietType.VEGETARIAN)
    # Non-vegetarian item inserted into vegetarian plan
    item = create_meal_item("grilled_chicken_breast", 120.0)
    meal = Meal(meal_type="lunch", items=[item])
    plan = DailyMealPlan(plan_id="test_plan", meals=[meal])

    res = verifier.verify_plan(plan, profile)
    assert not res.is_valid
    assert any("Non-veg" in v or "violates Vegetarian" in v for v in res.constraint_violations)


def test_verifier_flags_allergen(verifier):
    profile = UserProfile(diet_type=DietType.VEGETARIAN, allergies=["dairy"])
    # Palak paneer contains dairy
    item = create_meal_item("palak_paneer", 150.0)
    meal = Meal(meal_type="lunch", items=[item])
    plan = DailyMealPlan(plan_id="test_plan", meals=[meal])

    res = verifier.verify_plan(plan, profile)
    assert not res.is_valid
    assert any("Allergen conflict" in v for v in res.constraint_violations)


def test_verifier_passes_compliant_plan(verifier):
    profile = UserProfile(diet_type=DietType.VEGAN, daily_budget_inr=300.0)
    item1 = create_meal_item("roti_whole_wheat", 60.0)
    item2 = create_meal_item("dal_moong_tadka", 150.0)
    item3 = create_meal_item("cucumber_tomato_salad", 100.0)
    meal1 = Meal(meal_type="lunch", items=[item1, item2, item3])
    meal2 = Meal(meal_type="dinner", items=[item1, item2, item3])
    # Add sufficient calories to satisfy safe adult floor
    meal3 = Meal(meal_type="breakfast", items=[item1, item2])

    plan = DailyMealPlan(plan_id="valid_plan", meals=[meal1, meal2, meal3])
    res = verifier.verify_plan(plan, profile)
    assert res.is_valid
    assert res.arithmetic_error_percent == 0.0
