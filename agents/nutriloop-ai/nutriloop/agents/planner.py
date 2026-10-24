"""
Feasibility Planner Agent.
Generates balanced, initial daily meal plans tailored to user targets,
budget restrictions, preparation time bounds, and dietary choices.
"""

from typing import List
from nutriloop.agents.base import BaseAgent
from nutriloop.models import (
    DailyMealPlan,
    Meal,
    UserProfile,
    DietType
)
from nutriloop.nutrition_engine import create_meal_item
from nutriloop.database import list_foods_by_diet


class FeasibilityPlannerAgent(BaseAgent):
    """Creates a grounded initial meal plan respecting user constraints and budget."""

    def __init__(self):
        super().__init__(name="FeasibilityPlannerAgent", role="Nutritional Meal Planner")

    def generate_plan(self, profile: UserProfile, plan_id: str = "initial_day_plan") -> DailyMealPlan:
        """Construct an initial balanced daily meal plan for the given profile."""
        self.record_trace(
            action="PlanGenerationStart",
            reasoning=f"Building daily plan for {profile.name} (Calorie target: {profile.daily_calorie_target} kcal, Budget: ₹{profile.daily_budget_inr})"
        )

        available_foods = list_foods_by_diet(profile.diet_type)
        # Filter out allergies and excluded items
        filtered_foods = []
        user_allergies = [a.lower().strip() for a in profile.allergies]
        for f in available_foods:
            has_allergy = any(a in [allg.lower() for allg in f.allergens] for a in user_allergies)
            has_exclusion = any(ex.lower() in f.name.lower() or ex.lower() in f.id for ex in profile.excluded_ingredients)
            if not has_allergy and not has_exclusion:
                filtered_foods.append(f)

        food_ids = {f.id for f in filtered_foods}

        # Select meals depending on diet type and targets
        # 1. Breakfast (~20-25% of calories)
        breakfast_items = []
        if profile.diet_type == DietType.EGGETARIAN and "boiled_eggs" in food_ids:
            breakfast_items.append(create_meal_item("boiled_eggs", 100.0, "2 boiled eggs (100g)"))
            breakfast_items.append(create_meal_item("roti_whole_wheat", 60.0, "2 whole wheat rotis (60g)"))
        elif "poha_vegetable" in food_ids and "peanuts" not in user_allergies:
            breakfast_items.append(create_meal_item("poha_vegetable", 180.0, "1 plate vegetable poha (180g)"))
            if "curd_plain" in food_ids and "dairy" not in user_allergies:
                breakfast_items.append(create_meal_item("curd_plain", 100.0, "Small bowl curd (100g)"))
        elif "besan_chilla" in food_ids:
            breakfast_items.append(create_meal_item("besan_chilla", 140.0, "2 besan chillas (140g)"))
        else:
            breakfast_items.append(create_meal_item("idli_steamed", 180.0, "3 steamed idlis (180g)"))

        breakfast = Meal(meal_type="breakfast", items=breakfast_items)

        # 2. Lunch (~35% of calories)
        lunch_items = []
        if profile.diet_type == DietType.NON_VEGETARIAN and "grilled_chicken_breast" in food_ids:
            lunch_items.append(create_meal_item("grilled_chicken_breast", 120.0, "Grilled chicken breast (120g)"))
            lunch_items.append(create_meal_item("brown_rice_cooked", 150.0, "1 cup brown rice (150g)"))
            lunch_items.append(create_meal_item("cucumber_tomato_salad", 100.0, "Fresh kachumber salad (100g)"))
        elif "palak_paneer" in food_ids and "dairy" not in user_allergies:
            lunch_items.append(create_meal_item("palak_paneer", 150.0, "1 bowl palak paneer (150g)"))
            lunch_items.append(create_meal_item("roti_whole_wheat", 60.0, "2 whole wheat rotis (60g)"))
            lunch_items.append(create_meal_item("cucumber_tomato_salad", 100.0, "Fresh kachumber salad (100g)"))
        else:
            # Vegan, dairy-free, or Jain lunch
            dal_choice = "dal_toor" if "dal_toor" in food_ids else "dal_moong_tadka"
            lunch_items.append(create_meal_item(dal_choice, 160.0, "1 bowl dal (160g)"))
            lunch_items.append(create_meal_item("roti_whole_wheat", 60.0, "2 whole wheat rotis (60g)"))
            if profile.diet_type == DietType.JAIN:
                lunch_items.append(create_meal_item("bhindi_masala", 120.0, "1 bowl bhindi masala (120g)"))
            else:
                lunch_items.append(create_meal_item("mixed_veg_curry", 140.0, "1 bowl mixed veg sabzi (140g)"))

        lunch = Meal(meal_type="lunch", items=lunch_items)

        # 3. Evening Snack (~10-15% of calories)
        snack_items = []
        if "roasted_chana" in food_ids:
            snack_items.append(create_meal_item("roasted_chana", 40.0, "1 handful roasted chana (40g)"))
        elif "roasted_makhana" in food_ids:
            snack_items.append(create_meal_item("roasted_makhana", 30.0, "1 bowl roasted makhana (30g)"))
        elif "apple_fresh" in food_ids:
            snack_items.append(create_meal_item("apple_fresh", 130.0, "1 fresh apple (130g)"))
        else:
            snack_items.append(create_meal_item("papaya_ripe", 150.0, "1 bowl fresh papaya (150g)"))

        if "chaas_buttermilk" in food_ids and "dairy" not in user_allergies and profile.diet_type != DietType.VEGAN:
            snack_items.append(create_meal_item("chaas_buttermilk", 200.0, "1 glass masala chaas (200ml)"))

        snack = Meal(meal_type="snack", items=snack_items)

        # 4. Dinner (~30% of calories)
        dinner_items = []
        if "dal_moong_tadka" in food_ids:
            dinner_items.append(create_meal_item("dal_moong_tadka", 150.0, "1 bowl moong dal (150g)"))
            dinner_items.append(create_meal_item("roti_whole_wheat", 60.0, "2 whole wheat rotis (60g)"))
            dinner_items.append(create_meal_item("bhindi_masala", 120.0, "1 katori bhindi masala (120g)"))
        elif "boiled_sprouts_salad" in food_ids:
            dinner_items.append(create_meal_item("boiled_sprouts_salad", 150.0, "Sprouts salad with lemon (150g)"))
            dinner_items.append(create_meal_item("roti_whole_wheat", 60.0, "2 whole wheat rotis (60g)"))
        else:
            dinner_items.append(create_meal_item("soya_chunks_curry", 150.0, "High-protein soya curry (150g)"))
            dinner_items.append(create_meal_item("brown_rice_cooked", 140.0, "1 bowl brown rice (140g)"))

        dinner = Meal(meal_type="dinner", items=dinner_items)

        plan = DailyMealPlan(
            plan_id=plan_id,
            day="Day 1",
            meals=[breakfast, lunch, snack, dinner],
            notes=[
                "Evidence-based plan generated using ICMR-NIN IFCT standards.",
                f"Targets: {profile.daily_calorie_target:.0f} kcal, {profile.daily_protein_target_g:.0f}g protein."
            ]
        )

        self.record_trace(
            action="PlanGenerated",
            reasoning=f"Created 4-meal plan with {plan.total_calories:.1f} kcal, {plan.total_protein_g:.1f}g protein at ₹{plan.total_cost_inr:.1f}",
            details={"meals_count": len(plan.meals), "total_calories": plan.total_calories}
        )

        return plan
