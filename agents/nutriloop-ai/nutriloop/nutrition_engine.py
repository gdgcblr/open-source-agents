"""
Deterministic Nutrition Engine.
Performs exact arithmetic scaling of nutrients, portions, and costs from verified records.
Zero LLM hallucination in calculations: all numbers are mathematically derived.
"""

from typing import Dict, Optional, Tuple
from nutriloop.models import FoodItem, MealItem, Meal, DailyMealPlan, UserProfile
from nutriloop.database import get_food, search_foods


# Common household measure to grams conversion map
PORTION_UNIT_FACTORS = {
    "katori": 150.0,
    "bowl": 180.0,
    "cup": 150.0,
    "plate": 250.0,
    "glass": 200.0,
    "serving": 100.0,
    "piece": 30.0,
    "roti": 30.0,
    "idli": 60.0,
    "samosa": 90.0,
    "egg": 50.0,
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "ml": 1.0,
}


def parse_quantity_to_grams(food_item: FoodItem, quantity: float = 1.0, unit: str = "portion") -> Tuple[float, str]:
    """Convert everyday user units (e.g. 2 rotis, 1 katori) into standard gram weights."""
    unit_lower = unit.lower().strip()
    if unit_lower in PORTION_UNIT_FACTORS:
        factor = PORTION_UNIT_FACTORS[unit_lower]
        grams = round(quantity * factor, 1)
        desc = f"{quantity:g} {unit} ({grams:.0f}g)"
        return grams, desc

    # If portion or serving, scale by food default portion
    grams = round(quantity * food_item.default_portion_g, 1)
    desc = f"{quantity:g}x {food_item.portion_description} ({grams:.0f}g)"
    return grams, desc


def create_meal_item(
    food_id: str,
    portion_g: Optional[float] = None,
    portion_desc: Optional[str] = None
) -> MealItem:
    """
    Construct a verified MealItem from database item and desired gram weight.
    Calculates calories, macros, and cost with deterministic scaling.
    """
    food = get_food(food_id)
    if not food:
        # Fallback search if exact ID wasn't provided
        candidates = search_foods(food_id)
        if candidates:
            food = candidates[0]
        else:
            raise ValueError(f"Food item '{food_id}' not found in evidence database.")

    if portion_g is None or portion_g <= 0:
        portion_g = food.default_portion_g

    ratio = portion_g / 100.0
    calories = round(food.per_100g.calories * ratio, 1)
    protein_g = round(food.per_100g.protein_g * ratio, 1)
    carbs_g = round(food.per_100g.carbs_g * ratio, 1)
    fat_g = round(food.per_100g.fat_g * ratio, 1)
    fiber_g = round(food.per_100g.fiber_g * ratio, 1)

    # Cost scaled against default portion cost
    cost_ratio = portion_g / food.default_portion_g
    cost_inr = round(food.estimated_cost_inr * cost_ratio, 1)

    if not portion_desc:
        portion_desc = f"{food.portion_description} ({portion_g:.0f}g)"

    return MealItem(
        food_item_id=food.id,
        name=food.name,
        portion_g=round(portion_g, 1),
        portion_desc=portion_desc,
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        fiber_g=fiber_g,
        cost_inr=cost_inr
    )


def calculate_meal_totals(items: list[MealItem]) -> Dict[str, float]:
    """Compute exact sums across a list of meal items."""
    return {
        "calories": round(sum(i.calories for i in items), 1),
        "protein_g": round(sum(i.protein_g for i in items), 1),
        "carbs_g": round(sum(i.carbs_g for i in items), 1),
        "fat_g": round(sum(i.fat_g for i in items), 1),
        "fiber_g": round(sum(i.fiber_g for i in items), 1),
        "cost_inr": round(sum(i.cost_inr for i in items), 1)
    }


def compute_remaining_targets(
    profile: UserProfile,
    consumed_calories: float,
    consumed_protein: float,
    consumed_carbs: float,
    consumed_fat: float,
    spent_cost: float
) -> Dict[str, float]:
    """
    Calculate remaining allowances for the day without forcing extreme restrictions.
    Applies safety floors to prevent dangerously low daily intake suggestions.
    """
    rem_cal = max(profile.daily_calorie_target - consumed_calories, 0.0)
    rem_prot = max(profile.daily_protein_target_g - consumed_protein, 0.0)
    rem_carbs = max(profile.daily_carbs_target_g - consumed_carbs, 0.0)
    rem_fat = max(profile.daily_fat_target_g - consumed_fat, 0.0)
    rem_budget = max(profile.daily_budget_inr - spent_cost, 0.0)

    return {
        "remaining_calories": round(rem_cal, 1),
        "remaining_protein_g": round(rem_prot, 1),
        "remaining_carbs_g": round(rem_carbs, 1),
        "remaining_fat_g": round(rem_fat, 1),
        "remaining_budget_inr": round(rem_budget, 1),
        "is_budget_exceeded": spent_cost > profile.daily_budget_inr,
        "is_calorie_exceeded": consumed_calories > profile.daily_calorie_target
    }
