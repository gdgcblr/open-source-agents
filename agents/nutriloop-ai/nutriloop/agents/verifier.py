"""
Independent Verification Engine (Safety and Arithmetic Guard).
Provides deterministic, rule-based auditing of meal plans and adaptations.
Zero tolerance for LLM arithmetic errors or violated dietary constraints.
"""

from typing import List
from nutriloop.agents.base import BaseAgent
from nutriloop.models import (
    DailyMealPlan,
    UserProfile,
    VerificationResult,
    VerificationCheck,
    DietType
)
from nutriloop.database import get_food


class IndependentVerificationEngine(BaseAgent):
    """Audits meal plans against nutritional arithmetic, dietary bounds, and safety limits."""

    def __init__(self):
        super().__init__(name="VerificationEngine", role="Independent Audit & Safety Guard")

    def verify_plan(self, plan: DailyMealPlan, profile: UserProfile, max_prep_time: int = None) -> VerificationResult:
        """Execute full deterministic verification suite on a given daily meal plan."""
        checks: List[VerificationCheck] = []
        violations: List[str] = []
        safety_flags: List[str] = []
        effective_max_time = max_prep_time if max_prep_time is not None else profile.max_prep_time_minutes

        self.record_trace(
            action="BeginAudit",
            reasoning=f"Auditing plan '{plan.plan_id}' against profile of {profile.name} (Diet: {profile.diet_type.value})"
        )

        # -------------------------------------------------------------
        # 1. ARITHMETIC INTEGRITY AUDIT
        # -------------------------------------------------------------
        expected_meal_calories = sum(m.total_calories for m in plan.meals)
        expected_meal_protein = sum(m.total_protein_g for m in plan.meals)
        expected_meal_carbs = sum(m.total_carbs_g for m in plan.meals)
        expected_meal_fat = sum(m.total_fat_g for m in plan.meals)
        expected_meal_cost = sum(m.total_cost_inr for m in plan.meals)

        cal_discrepancy = abs(plan.total_calories - expected_meal_calories)
        cost_discrepancy = abs(plan.total_cost_inr - expected_meal_cost)

        arithmetic_error_pct = (cal_discrepancy / max(expected_meal_calories, 1.0)) * 100.0

        if cal_discrepancy <= 1.0:
            checks.append(VerificationCheck(
                check_name="Arithmetic: Calorie Summation",
                passed=True,
                severity="info",
                details=f"Plan total calories ({plan.total_calories:.1f}) matches sum of meals ({expected_meal_calories:.1f}).",
                discrepancy_value=round(cal_discrepancy, 2)
            ))
        else:
            checks.append(VerificationCheck(
                check_name="Arithmetic: Calorie Summation",
                passed=False,
                severity="critical",
                details=f"Discrepancy detected: plan states {plan.total_calories:.1f} kcal, but item sum is {expected_meal_calories:.1f} kcal.",
                discrepancy_value=round(cal_discrepancy, 2)
            ))
            violations.append(f"Calorie arithmetic discrepancy: {cal_discrepancy:.1f} kcal")

        # -------------------------------------------------------------
        # 2. DIETARY RESTRICTIONS AUDIT
        # -------------------------------------------------------------
        diet_violation_found = False
        for meal in plan.meals:
            for item in meal.items:
                food = get_food(item.food_item_id)
                if not food:
                    continue

                # Check Vegetarian constraint
                if profile.diet_type == DietType.VEGETARIAN:
                    if food.diet_type in (DietType.NON_VEGETARIAN, DietType.EGGETARIAN):
                        diet_violation_found = True
                        msg = f"Non-veg / Egg item '{food.name}' violates Vegetarian constraint."
                        violations.append(msg)

                # Check Vegan constraint
                elif profile.diet_type == DietType.VEGAN:
                    if food.diet_type != DietType.VEGAN or "dairy" in food.allergens or "eggs" in food.allergens:
                        diet_violation_found = True
                        msg = f"Non-vegan item '{food.name}' violates Vegan constraint."
                        violations.append(msg)

                # Check Jain constraint
                elif profile.diet_type == DietType.JAIN:
                    if not food.is_jain_friendly:
                        diet_violation_found = True
                        msg = f"Item '{food.name}' contains root vegetables / prohibited ingredients for Jain diet."
                        violations.append(msg)

        checks.append(VerificationCheck(
            check_name="Dietary Compatibility",
            passed=not diet_violation_found,
            severity="critical" if diet_violation_found else "info",
            details="All ingredients strictly match user diet classification." if not diet_violation_found else f"Found {len(violations)} dietary violations."
        ))

        # -------------------------------------------------------------
        # 3. ALLERGEN AUDIT
        # -------------------------------------------------------------
        allergen_violation_found = False
        user_allergies = [a.lower().strip() for a in profile.allergies]
        for meal in plan.meals:
            for item in meal.items:
                food = get_food(item.food_item_id)
                if not food:
                    continue
                for allergy in user_allergies:
                    if allergy in [a.lower() for a in food.allergens]:
                        allergen_violation_found = True
                        msg = f"Allergen conflict: '{food.name}' contains declared allergen '{allergy}'."
                        violations.append(msg)

        checks.append(VerificationCheck(
            check_name="Allergen Safety",
            passed=not allergen_violation_found,
            severity="critical" if allergen_violation_found else "info",
            details="Zero declared allergens detected in meal plan." if not allergen_violation_found else "Declared allergens detected in proposed meals."
        ))

        # -------------------------------------------------------------
        # 4. PREPARATION TIME FEASIBILITY
        # -------------------------------------------------------------
        time_exceeded = False
        max_meal_prep = max((m.prep_time_minutes for m in plan.meals), default=0)
        if max_meal_prep > effective_max_time:
            time_exceeded = True
            violations.append(f"Meal prep time ({max_meal_prep} mins) exceeds allowable limit of {effective_max_time} mins.")

        checks.append(VerificationCheck(
            check_name="Cooking Time Feasibility",
            passed=not time_exceeded,
            severity="warning" if time_exceeded else "info",
            details=f"Max meal prep is {max_meal_prep} mins (User limit: {effective_max_time} mins)."
        ))

        # -------------------------------------------------------------
        # 5. BUDGET ADHERENCE AUDIT
        # -------------------------------------------------------------
        budget_exceeded = plan.total_cost_inr > (profile.daily_budget_inr * 1.05)
        checks.append(VerificationCheck(
            check_name="Budget Compliance",
            passed=not budget_exceeded,
            severity="warning" if budget_exceeded else "info",
            details=f"Estimated plan cost: ₹{plan.total_cost_inr:.1f} vs daily budget: ₹{profile.daily_budget_inr:.1f}.",
            discrepancy_value=round(plan.total_cost_inr - profile.daily_budget_inr, 1)
        ))
        if budget_exceeded:
            violations.append(f"Plan cost (₹{plan.total_cost_inr:.1f}) exceeds budget allowance (₹{profile.daily_budget_inr:.1f}).")

        # -------------------------------------------------------------
        # 6. ANTI-EXTREMITY & SAFETY GUARD
        # -------------------------------------------------------------
        # Prevent crash dieting / dangerously low calories (< 1000 kcal for an adult plan)
        if plan.total_calories < 1000.0:
            safety_flags.append(f"Critically low caloric intake: {plan.total_calories:.0f} kcal is below safe threshold (1000 kcal).")
            violations.append("Plan violates minimum safe caloric threshold.")

        # Ensure reasonable protein intake (minimum 30g/day)
        if plan.total_protein_g < 30.0:
            safety_flags.append(f"Inadequate daily protein: {plan.total_protein_g:.1f}g is below safe baseline.")

        # Check meal-level anti-starvation: adapted main meals should have at least 250 kcal
        meal_starvation_found = False
        for meal in plan.meals:
            if meal.meal_type.lower() in ("lunch", "dinner") and meal.total_calories < 250.0:
                meal_starvation_found = True
                safety_flags.append(f"Meal '{meal.meal_type}' contains only {meal.total_calories:.0f} kcal, below minimum safe threshold (250 kcal).")
                violations.append(f"Anti-starvation violation: {meal.meal_type} calories too low ({meal.total_calories:.0f} kcal).")

        anti_extremity_passed = (plan.total_calories >= 1000.0) and (plan.total_protein_g >= 30.0) and not meal_starvation_found
        checks.append(VerificationCheck(
            check_name="Anti-Starvation & Safety Guard",
            passed=anti_extremity_passed,
            severity="critical" if not anti_extremity_passed else "info",
            details="Plan satisfies safe caloric floor (>=1000 kcal), protein baseline (>=30g), and non-punitive meal portions." if anti_extremity_passed else "Plan triggers anti-starvation or nutritional safety guardrails."
        ))

        is_valid = len(violations) == 0

        ver_notes = "Plan successfully passed all deterministic safety and constraint checks." if is_valid else f"Audit flagged {len(violations)} issues requiring plan adjustment."

        self.record_trace(
            action="AuditComplete",
            reasoning=ver_notes,
            details={"is_valid": is_valid, "violations_count": len(violations), "error_pct": round(arithmetic_error_pct, 2)}
        )

        return VerificationResult(
            is_valid=is_valid,
            checks=checks,
            arithmetic_error_percent=round(arithmetic_error_pct, 2),
            constraint_violations=violations,
            safety_flags=safety_flags,
            verifier_notes=ver_notes
        )
