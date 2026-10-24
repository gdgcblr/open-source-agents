"""
Unit tests for Adaptive Replanner Agent.
Tests lifestyle disruption response, ingredient substitution, and time crunch adaptation.
"""

import pytest
from nutriloop.agents.adaptive_replanner import AdaptiveReplannerAgent
from nutriloop.agents.planner import FeasibilityPlannerAgent
from nutriloop.models import (
    UserProfile,
    FoodLogEntry,
    DisruptionEvent,
    DietType
)
from nutriloop.nutrition_engine import create_meal_item


@pytest.fixture
def replanner():
    return AdaptiveReplannerAgent()


@pytest.fixture
def planner():
    return FeasibilityPlannerAgent()


def test_replanner_handles_missing_paneer(replanner, planner):
    profile = UserProfile(diet_type=DietType.VEGETARIAN)
    initial_plan = planner.generate_plan(profile)

    disruption = DisruptionEvent(
        type="missing_ingredient",
        description="Ran out of paneer",
        data={"unavailable": ["paneer"]}
    )

    adapted = replanner.replan(
        current_plan=initial_plan,
        profile=profile,
        food_logs=[],
        disruptions=[disruption]
    )

    # Verify no paneer items in adapted plan
    for m in adapted.meals:
        for item in m.items:
            assert "paneer" not in item.name.lower()
            assert "paneer" not in item.food_item_id.lower()


def test_replanner_handles_unplanned_snack(replanner, planner):
    profile = UserProfile(daily_calorie_target=1800.0, diet_type=DietType.VEGETARIAN)
    initial_plan = planner.generate_plan(profile)

    # User ate 1 samosa (308 kcal)
    samosa_item = create_meal_item("samosa_fried", 90.0)
    snack_log = FoodLogEntry(
        meal_type="snack",
        description="1 samosa",
        consumed_items=[samosa_item],
        total_calories=samosa_item.calories,
        is_unplanned=True
    )

    adapted = replanner.replan(
        current_plan=initial_plan,
        profile=profile,
        food_logs=[snack_log],
        disruptions=[DisruptionEvent(type="unplanned_meal", description="Eats samosa")]
    )

    # Verify snack slot now contains the logged samosa
    snack_meal = next(m for m in adapted.meals if m.meal_type == "snack")
    assert any("samosa" in i.name.lower() for i in snack_meal.items)
    # Total calories are non-zero and dinner was not starved
    dinner_meal = next(m for m in adapted.meals if m.meal_type == "dinner")
    assert dinner_meal.total_calories >= 250.0
