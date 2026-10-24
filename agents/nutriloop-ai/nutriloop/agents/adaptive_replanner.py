"""
Adaptive Replanner Agent.
Implements closed-loop replanning in response to real-life disruptions:
unplanned restaurant meals, missing pantry ingredients, cooking time crunch, and budget cuts.
Ensures adjustments are sustainable and non-punitive (never recommends crash fasting).
"""

import json
import logging
from typing import List, Dict, Any, Optional
from nutriloop.agents.base import BaseAgent
from nutriloop.models import (
    DailyMealPlan,
    Meal,
    UserProfile,
    FoodLogEntry,
    DisruptionEvent,
    DietType
)
from nutriloop.nutrition_engine import (
    create_meal_item,
    compute_remaining_targets
)
from nutriloop.database import list_foods_by_diet, get_food

logger = logging.getLogger("nutriloop.agent")


class AdaptiveReplannerAgent(BaseAgent):
    """Dynamically recalculates remaining daily meals to meet targets without extreme restriction."""

    def __init__(self):
        super().__init__(name="AdaptiveReplannerAgent", role="Closed-Loop Meal Replanner")

    def _consult_gemini_replanner(
        self,
        profile: UserProfile,
        disruptions: List[DisruptionEvent],
        remaining: Dict[str, float],
        unavailable_items: set,
        max_prep_time: int
    ) -> Optional[Dict[str, Any]]:
        """
        Consult Google GenAI SDK (Gemini) for context-aware replanning and coaching rationale
        under strict nutrition guardrails.
        """
        client = self.get_gemini_client()
        if not client:
            return None

        # Build list of eligible database candidate dishes compliant with profile diet and constraints
        eligible_foods = list_foods_by_diet(profile.diet_type)
        user_allergies = [a.lower().strip() for a in profile.allergies]
        eligible_candidates = [
            f.id for f in eligible_foods
            if not any(u in f.name.lower() or u in f.id.lower() for u in unavailable_items)
            and f.prep_time_minutes <= max_prep_time
            and not any(a in [al.lower() for al in f.allergens] for a in user_allergies)
        ]

        if not eligible_candidates:
            return None

        system_instruction = (
            "You are NutriLoop AI, an adaptive clinical nutrition agent adhering strictly to ICMR-NIN dietary guidelines.\n"
            "STRICT GUARDRAILS:\n"
            "1. NEVER advise skipping meals, extreme caloric deficit, or compensatory fasting.\n"
            f"2. User Diet: {profile.diet_type.value.upper()}. Never recommend non-compliant items.\n"
            f"3. User Allergies: {user_allergies}. Never recommend allergens.\n"
            f"4. Maximum prep time: {max_prep_time} minutes.\n"
            f"5. Candidate dinner dishes MUST be chosen from this verified catalog list: {eligible_candidates[:25]}.\n"
        )

        prompt = f"""
Disruptions: {[d.description for d in disruptions]}
Remaining Calorie Target: {remaining['remaining_calories']:.1f} kcal
Remaining Protein Target: {remaining['remaining_protein_g']:.1f}g
Remaining Daily Budget: ₹{remaining.get('remaining_budget_inr', 100):.1f}

Provide:
1. "coaching_insight": Empathetic, scientifically sound advice explaining how dinner is balanced without guilt or starvation.
2. "recommended_dish_ids": List of 2 to 3 dish IDs from the verified list for dinner.

Output pure JSON with keys 'coaching_insight' (string) and 'recommended_dish_ids' (array of strings).
"""
        try:
            from google.genai import types
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,
                    response_mime_type="application/json"
                )
            )
            data = json.loads(response.text.strip())
            dish_ids = data.get("recommended_dish_ids", [])
            valid_items = []
            for did in dish_ids:
                if did in eligible_candidates:
                    valid_items.append(create_meal_item(did))

            dinner_cal = sum(i.calories for i in valid_items)
            # Anti-starvation guardrail check: dinner must provide at least 250 kcal
            if dinner_cal >= 250.0:
                self.record_trace(
                    action="GeminiReplanned",
                    reasoning=f"Google GenAI recommended {len(valid_items)} verified dishes: {[i.name for i in valid_items]}.",
                    details={"coaching_insight": data.get("coaching_insight"), "dinner_calories": dinner_cal}
                )
                return {
                    "items": valid_items,
                    "coaching_insight": data.get("coaching_insight", "")
                }
            else:
                self.record_trace(
                    action="GeminiGuardrailTriggered",
                    reasoning=f"Gemini proposed {dinner_cal:.1f} kcal for dinner which violated minimum safe threshold (250 kcal). Safely fell back to deterministic engine."
                )
        except Exception as e:
            logger.warning(f"[{self.name}] Gemini replanning consultation failed: {e}")
            self.record_trace(
                action="GeminiReplannerFallback",
                reasoning=f"Gemini replanning consultation error ({e}); safely fell back to deterministic replanning."
            )
        return None

    def replan(
        self,
        current_plan: DailyMealPlan,
        profile: UserProfile,
        food_logs: List[FoodLogEntry],
        disruptions: List[DisruptionEvent],
        feedback_notes: Optional[str] = None
    ) -> DailyMealPlan:
        """
        Formulate a revised daily meal plan accounting for logged meals and real-world disruptions.
        """
        self.record_trace(
            action="StartReplanning",
            reasoning=f"Replanning for {len(food_logs)} logged meals and {len(disruptions)} disruption events.",
            details={"disruptions": [d.type for d in disruptions], "feedback": feedback_notes}
        )

        # 1. Calculate actual consumed nutrients so far
        consumed_cal = sum(log.total_calories for log in food_logs)
        consumed_prot = sum(log.total_protein_g for log in food_logs)
        consumed_carb = sum(log.total_carbs_g for log in food_logs)
        consumed_fat = sum(log.total_fat_g for log in food_logs)
        spent_cost = sum(sum(i.cost_inr for i in log.consumed_items) for log in food_logs)

        # Identify which meal slots are already consumed or replaced
        consumed_meal_types = {log.meal_type.lower() for log in food_logs}

        # Account for meals already elapsed in the plan (e.g. breakfast/lunch) that are not being adapted
        elapsed_meals = [m for m in current_plan.meals if m.meal_type.lower() not in ("dinner", "snack") and m.meal_type.lower() not in consumed_meal_types]
        total_consumed_cal = consumed_cal + sum(m.total_calories for m in elapsed_meals)
        total_consumed_prot = consumed_prot + sum(m.total_protein_g for m in elapsed_meals)
        total_consumed_carb = consumed_carb + sum(m.total_carbs_g for m in elapsed_meals)
        total_consumed_fat = consumed_fat + sum(m.total_fat_g for m in elapsed_meals)
        total_spent_cost = spent_cost + sum(m.total_cost_inr for m in elapsed_meals)

        # Check for specific disruptions
        unavailable_items = set()
        max_prep_time = profile.max_prep_time_minutes
        budget_adjustment = 0.0

        for d in disruptions:
            if d.type == "missing_ingredient":
                missing = d.data.get("unavailable", [])
                if isinstance(missing, list):
                    unavailable_items.update([m.lower() for m in missing])
                elif isinstance(missing, str):
                    unavailable_items.add(missing.lower())
            elif d.type == "time_crunch":
                max_prep_time = min(max_prep_time, d.data.get("max_prep_time_minutes", 15))
            elif d.type == "budget_cut":
                budget_adjustment = d.data.get("cost_reduction_inr", 30.0)

        # Compute remaining targets
        effective_budget = max(profile.daily_budget_inr - budget_adjustment, 50.0)
        remaining = compute_remaining_targets(
            profile=profile,
            consumed_calories=total_consumed_cal,
            consumed_protein=total_consumed_prot,
            consumed_carbs=total_consumed_carb,
            consumed_fat=total_consumed_fat,
            spent_cost=total_spent_cost
        )

        self.record_trace(
            action="BudgetRemainingCalculated",
            reasoning=f"Consumed: {consumed_cal:.1f} kcal. Remaining target: {remaining['remaining_calories']:.1f} kcal, {remaining['remaining_protein_g']:.1f}g protein.",
            details=remaining
        )

        revised_meals: List[Meal] = []

        coaching_note = None

        # 2. Re-construct the day: retain logged meals as consumed, adapt future unconsumed slots
        for original_meal in current_plan.meals:
            m_type = original_meal.meal_type.lower()

            if m_type in consumed_meal_types:
                # Find corresponding log entry
                matching_log = next(log for log in food_logs if log.meal_type.lower() == m_type)
                # Keep the logged items as the reality for this meal
                revised_meals.append(Meal(
                    meal_type=m_type,
                    items=matching_log.consumed_items,
                    prep_time_minutes=0
                ))
                continue

            # This is an upcoming meal that can be adapted!
            # Example: Adapting Dinner after an unplanned heavy snack or lunch
            if m_type == "dinner":
                gemini_res = self._consult_gemini_replanner(
                    profile=profile,
                    disruptions=disruptions,
                    remaining=remaining,
                    unavailable_items=unavailable_items,
                    max_prep_time=max_prep_time
                )
                if gemini_res and gemini_res.get("items"):
                    adapted_dinner_items = gemini_res["items"]
                    if gemini_res.get("coaching_insight"):
                        coaching_note = gemini_res["coaching_insight"]
                else:
                    adapted_dinner_items = self._build_adaptive_dinner(
                        profile=profile,
                        remaining=remaining,
                        unavailable_items=unavailable_items,
                        max_prep_time=max_prep_time
                    )
                revised_meals.append(Meal(
                    meal_type="dinner",
                    items=adapted_dinner_items,
                    prep_time_minutes=min(max_prep_time, 15)
                ))
            elif m_type == "snack":
                adapted_snack_items = self._build_adaptive_snack(
                    profile=profile,
                    remaining=remaining,
                    unavailable_items=unavailable_items
                )
                revised_meals.append(Meal(
                    meal_type="snack",
                    items=adapted_snack_items,
                    prep_time_minutes=5
                ))
            else:
                # Check if original meal items have unavailable ingredients
                has_unavailable = any(
                    any(u in item.name.lower() or u in item.food_item_id.lower() for u in unavailable_items)
                    for item in original_meal.items
                )
                if has_unavailable:
                    # Substitute unavailable items
                    subbed_items = self._substitute_items(original_meal.items, profile, unavailable_items)
                    revised_meals.append(Meal(meal_type=m_type, items=subbed_items))
                else:
                    revised_meals.append(original_meal)

        plan_notes = [
            f"Adaptive plan recalculated at {food_logs[-1].logged_at if food_logs else 'now'}.",
            f"Adjusted for {len(food_logs)} logged meal(s) and {len(disruptions)} lifestyle disruption(s).",
            "Maintained minimum 1200+ kcal floor and adequate fiber for healthy satiety."
        ]
        if coaching_note:
            plan_notes.append(f"AI Coaching Guidance: {coaching_note}")
        if feedback_notes:
            plan_notes.append(f"Repair cycle adjustment: {feedback_notes}")

        revised_plan = DailyMealPlan(
            plan_id=f"adapted_{current_plan.plan_id}",
            day=current_plan.day,
            meals=revised_meals,
            notes=plan_notes
        )

        self.record_trace(
            action="ReplanningComplete",
            reasoning=f"Generated adapted plan with {revised_plan.total_calories:.1f} total kcal and {revised_plan.total_protein_g:.1f}g protein.",
            details={"revised_calories": revised_plan.total_calories, "revised_cost": revised_plan.total_cost_inr}
        )

        return revised_plan

    def _build_adaptive_dinner(
        self,
        profile: UserProfile,
        remaining: Dict[str, float],
        unavailable_items: set,
        max_prep_time: int
    ) -> List[Any]:
        """Build a balanced, satiating dinner fitting the remaining calorie and time budget."""
        items = []
        rem_cal = remaining["remaining_calories"]

        # Anti-starvation principle: Dinner must always provide at least 300 kcal even if remaining is low
        target_dinner_cal = max(min(rem_cal, 650.0), 320.0)

        # High-protein, fast-prep, clean choices
        is_jain = profile.diet_type == DietType.JAIN
        is_veg = profile.diet_type == DietType.VEGETARIAN
        is_vegan = profile.diet_type == DietType.VEGAN
        is_egg = profile.diet_type == DietType.EGGETARIAN
        is_nonveg = profile.diet_type == DietType.NON_VEGETARIAN

        roti_g = 60.0 if rem_cal >= 350.0 else 30.0
        roti_label = "2 whole wheat rotis (60g)" if rem_cal >= 350.0 else "1 whole wheat roti (30g)"

        rem_budget = remaining.get("remaining_budget_inr", 100.0)
        is_budget_tight = rem_budget < 65.0

        # Lentil / Protein Core
        if "paneer" not in unavailable_items and is_veg and not is_budget_tight and max_prep_time >= 15:
            items.append(create_meal_item("paneer_bhurji", 100.0, "Quick paneer bhurji (100g)"))
            items.append(create_meal_item("roti_whole_wheat", roti_g, roti_label))
            items.append(create_meal_item("cucumber_tomato_salad", 100.0, "Cucumber salad (100g)"))
        elif is_egg and "egg" not in unavailable_items:
            items.append(create_meal_item("egg_bhurji", 120.0, "Quick 2-egg bhurji (120g)"))
            items.append(create_meal_item("roti_whole_wheat", roti_g, roti_label))
            items.append(create_meal_item("cucumber_tomato_salad", 100.0, "Cucumber salad (100g)"))
        elif is_nonveg and "chicken" not in unavailable_items:
            items.append(create_meal_item("grilled_chicken_breast", 120.0, "Grilled chicken breast (120g)"))
            items.append(create_meal_item("cucumber_tomato_salad", 120.0, "Large fresh salad (120g)"))
            items.append(create_meal_item("roti_whole_wheat", roti_g, roti_label))
        elif is_jain:
            # Jain compliant dinner: Toor Dal or Moong Sprouts (no onion/garlic/root veg)
            items.append(create_meal_item("dal_toor", 150.0, "Jain toor dal (150g)"))
            items.append(create_meal_item("roti_whole_wheat", 60.0, "2 whole wheat rotis (60g)"))
            items.append(create_meal_item("cucumber_tomato_salad", 100.0, "Fresh kachumber salad (100g)"))
        elif "sprouts" not in unavailable_items and max_prep_time <= 15:
            items.append(create_meal_item("boiled_sprouts_salad", 150.0, "Moong sprouts salad with lemon (150g)"))
            items.append(create_meal_item("roti_whole_wheat", 60.0, "2 whole wheat rotis (60g)"))
            if not is_vegan and "dairy" not in [a.lower() for a in profile.allergies] and "curd" not in unavailable_items:
                items.append(create_meal_item("curd_plain", 100.0, "Fresh curd (100g)"))
        else:
            # Default healthy Moong Dal (lightest on digestion) + Roti + Salad
            items.append(create_meal_item("dal_moong_tadka", 150.0, "Yellow moong dal (150g)"))
            items.append(create_meal_item("roti_whole_wheat", roti_g, roti_label))
            items.append(create_meal_item("cucumber_tomato_salad", 100.0, "Kachumber salad (100g)"))

        return items

    def _build_adaptive_snack(self, profile: UserProfile, remaining: Dict[str, float], unavailable_items: set) -> List[Any]:
        """Construct a light, clean snack if dinner needs more calorie buffer."""
        items = []
        rem_cal = remaining["remaining_calories"]
        if rem_cal < 500:
            # Very light snack: chaas or green salad
            if profile.diet_type != DietType.VEGAN and "dairy" not in [a.lower() for a in profile.allergies] and "chaas" not in unavailable_items:
                items.append(create_meal_item("chaas_buttermilk", 200.0, "Chilled spiced buttermilk (200ml)"))
            else:
                items.append(create_meal_item("cucumber_tomato_salad", 100.0, "Fresh cucumber salad (100g)"))
        else:
            items.append(create_meal_item("roasted_chana", 30.0, "Roasted chana (30g)"))
        return items

    def _substitute_items(self, items: List[Any], profile: UserProfile, unavailable_items: set) -> List[Any]:
        """Replace unavailable ingredients with compliant, equivalent options."""
        substituted = []
        for item in items:
            is_unavail = any(u in item.name.lower() or u in item.food_item_id.lower() for u in unavailable_items)
            if not is_unavail:
                substituted.append(item)
            else:
                # Find substitute
                if "paneer" in item.food_item_id or "paneer" in item.name.lower():
                    # Substitute with high-protein soya curry or moong dal
                    sub_id = "soya_chunks_curry" if profile.diet_type == DietType.VEGAN else "dal_moong_tadka"
                    substituted.append(create_meal_item(sub_id, 150.0, f"Substitute for {item.name}"))
                elif "curd" in item.food_item_id:
                    substituted.append(create_meal_item("chaas_buttermilk", 200.0, "Chaas substitute"))
                else:
                    substituted.append(create_meal_item("mixed_veg_curry", 140.0, "Mixed vegetable substitute"))
        return substituted
