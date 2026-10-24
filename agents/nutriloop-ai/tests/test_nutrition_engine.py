"""
Unit tests for Deterministic Nutrition Engine.
Validates exact arithmetic, portion conversions, and zero numerical hallucinations.
"""

import pytest
from nutriloop.nutrition_engine import (
    create_meal_item,
    calculate_meal_totals,
    compute_remaining_targets,
    parse_quantity_to_grams
)
from nutriloop.database import get_food
from nutriloop.models import UserProfile, DietType


def test_create_meal_item_exact_scaling():
    food = get_food("roti_whole_wheat")
    assert food is not None
    # 60g portion (2 rotis)
    item = create_meal_item("roti_whole_wheat", portion_g=60.0)

    # 297 kcal per 100g * 0.6 = 178.2 kcal
    expected_cal = round((food.per_100g.calories * 60.0) / 100.0, 1)
    expected_prot = round((food.per_100g.protein_g * 60.0) / 100.0, 1)

    assert item.calories == expected_cal
    assert item.protein_g == expected_prot
    assert item.portion_g == 60.0


def test_portion_parsing_katori_and_counts():
    food = get_food("dal_moong_tadka")
    grams, desc = parse_quantity_to_grams(food, quantity=2.0, unit="katori")
    assert grams == 300.0  # 2 * 150g
    assert "300g" in desc


def test_calculate_meal_totals():
    item1 = create_meal_item("roti_whole_wheat", 60.0)
    item2 = create_meal_item("dal_moong_tadka", 150.0)

    totals = calculate_meal_totals([item1, item2])
    assert totals["calories"] == round(item1.calories + item2.calories, 1)
    assert totals["protein_g"] == round(item1.protein_g + item2.protein_g, 1)


def test_compute_remaining_targets():
    profile = UserProfile(
        daily_calorie_target=2000.0,
        daily_protein_target_g=70.0,
        daily_budget_inr=250.0
    )
    rem = compute_remaining_targets(
        profile=profile,
        consumed_calories=600.0,
        consumed_protein=25.0,
        consumed_carbs=80.0,
        consumed_fat=20.0,
        spent_cost=70.0
    )
    assert rem["remaining_calories"] == 1400.0
    assert rem["remaining_protein_g"] == 45.0
    assert rem["remaining_budget_inr"] == 180.0
    assert not rem["is_calorie_exceeded"]
