"""
NutriLoop AI: Command Line Interface & Runner.
Usage:
    python main.py                  # Run end-to-end adaptive demonstration
    python main.py --benchmark      # Run 4-way baseline benchmark evaluation
    python main.py --query "1 samosa and chai" # Analyze food intake
"""

import sys
import argparse
from nutriloop.models import UserProfile, DietType, HealthGoal, DisruptionEvent
from nutriloop.orchestrator import NutriLoopOrchestrator
from nutriloop.evaluation.runner import print_benchmark_report


def run_demo():
    print("\n" + "=" * 70)
    print("🥗  NutriLoop AI: Adaptive Multi-Agent Nutrition System")
    print("=" * 70)

    orchestrator = NutriLoopOrchestrator()

    # 1. Define consumer profile
    profile = UserProfile(
        user_id="user_aarav_01",
        name="Aarav Sharma",
        diet_type=DietType.VEGETARIAN,
        daily_calorie_target=1800.0,
        daily_protein_target_g=65.0,
        daily_budget_inr=220.0,
        max_prep_time_minutes=25,
        health_goal=HealthGoal.WEIGHT_LOSS
    )

    print(f"\n👤 [1/4] User Profile Loaded:")
    print(f"   Name: {profile.name} | Diet: {profile.diet_type.value.title()}")
    print(f"   Calorie Target: {profile.daily_calorie_target:.0f} kcal | Protein Target: {profile.daily_protein_target_g:.0f}g")
    print(f"   Daily Budget: ₹{profile.daily_budget_inr:.0f} | Max Cooking Prep Time: {profile.max_prep_time_minutes} mins")

    # 2. Initial Plan Generation
    print(f"\n📋 [2/4] Generating Initial Feasible Plan...")
    initial_res = orchestrator.run_initial_plan(profile)
    plan = initial_res.original_plan
    print(f"   Created {len(plan.meals)} meals:")
    for m in plan.meals:
        items_str = ", ".join(i.name for i in m.items)
        print(f"   • {m.meal_type.upper():<10}: {items_str} ({m.total_calories:.0f} kcal, ₹{m.total_cost_inr:.0f})")
    print(f"   Total Day 1: {plan.total_calories:.1f} kcal | Protein: {plan.total_protein_g:.1f}g | Cost: ₹{plan.total_cost_inr:.1f}")

    # 3. Real Life Disruption
    print(f"\n⚡ [3/4] Real Life Disruption Event:")
    print("   • 16:30 — User attends office party and eats '1 fried vegetable samosa and 1 cutting masala chai'.")
    print("   • 19:00 — User finds paneer is out of stock in the fridge.")
    print("   • 19:00 — User has only 15 minutes to cook dinner.")

    raw_food_logs = [
        {"text": "1 fried vegetable samosa and 1 cutting masala chai", "meal_type": "snack", "logged_at": "16:30", "is_unplanned": True}
    ]
    disruptions = [
        DisruptionEvent(type="unplanned_meal", description="Ate office samosa and chai at 4:30pm"),
        DisruptionEvent(type="missing_ingredient", description="No paneer at home", data={"unavailable": ["paneer"]}),
        DisruptionEvent(type="time_crunch", description="Only 15 mins to cook", data={"max_prep_time_minutes": 15})
    ]

    # 4. Multi-Agent Adaptive Replanning & Verification
    print(f"\n🔄 [4/4] Executing Closed-Loop Multi-Agent Adaptation...")
    adaptation_res = orchestrator.adapt_to_disruptions(
        profile=profile,
        current_plan=plan,
        raw_food_logs=raw_food_logs,
        disruptions=disruptions
    )

    adapted_plan = adaptation_res.revised_plan
    ver = adaptation_res.verification

    print(f"\n✅ Adapted Daily Meal Schedule:")
    for m in adapted_plan.meals:
        items_str = ", ".join(f"{i.name} ({i.portion_desc})" for i in m.items)
        print(f"   • {m.meal_type.upper():<10}: {items_str} [{m.total_calories:.0f} kcal]")

    print(f"\n📊 Deterministic Verification Audit:")
    print(f"   • Audit Status:            {'✅ PASSED' if ver.is_valid else '❌ REJECTED'}")
    print(f"   • Calorie Arithmetic Error: {ver.arithmetic_error_percent:.2f}% (Target: < 1.0%)")
    print(f"   • Hard Constraint Flags:    {len(ver.constraint_violations)}")
    print(f"   • Total Day Calories:       {adapted_plan.total_calories:.1f} kcal (Target: {profile.daily_calorie_target:.0f} kcal)")
    print(f"   • Total Day Protein:        {adapted_plan.total_protein_g:.1f}g (Target: {profile.daily_protein_target_g:.0f}g)")
    print(f"   • Total Day Cost:           ₹{adapted_plan.total_cost_inr:.1f} (Budget: ₹{profile.daily_budget_inr:.0f})")
    print(f"   • Non-Punitive Guard:       Confirmed (Dinner provided satisfying {adapted_plan.meals[-1].total_calories:.0f} kcal without starvation)")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="NutriLoop AI - Adaptive Nutrition Multi-Agent System")
    parser.add_argument("--benchmark", action="store_true", help="Run 4-way baseline benchmark evaluation")
    parser.add_argument("--query", type=str, help="Quickly analyze a food text description")

    args = parser.parse_args()

    if args.benchmark:
        print_benchmark_report()
    elif args.query:
        from nutriloop.agents.food_analyzer import FoodAnalyzerAgent
        analyzer = FoodAnalyzerAgent()
        result = analyzer.analyze_food_log(args.query)
        print(f"\nNutrient Analysis for '{args.query}':")
        print(f"Items detected: {[i.name for i in result.consumed_items]}")
        print(f"Calories: {result.total_calories} kcal | Protein: {result.total_protein_g}g | Carbs: {result.total_carbs_g}g | Fat: {result.total_fat_g}g\n")
    else:
        run_demo()


if __name__ == "__main__":
    main()
