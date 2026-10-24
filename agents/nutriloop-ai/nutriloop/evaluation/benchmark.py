"""
NutriLoop Benchmark Dataset.
Synthetic consumer scenarios reflecting diverse Indian diets, lifestyle disruptions,
time bottlenecks, allergy restrictions, and tight economic budgets.
"""

from typing import List, Dict, Any
from pydantic import BaseModel
from nutriloop.models import (
    UserProfile,
    DietType,
    HealthGoal,
    DisruptionEvent
)


class BenchmarkScenario(BaseModel):
    """A standardized evaluation case with ground-truth constraints and disruption events."""
    id: str
    title: str
    description: str
    profile: UserProfile
    logged_food_texts: List[Dict[str, Any]]
    disruptions: List[DisruptionEvent]
    expected_hard_constraints: Dict[str, Any]


BENCHMARK_SCENARIOS: List[BenchmarkScenario] = [
    BenchmarkScenario(
        id="scenario_01_office_samosa_snack",
        title="College Student with Unexpected Canteen Samosa & Tea",
        description="Budget-conscious vegetarian student with 1800 kcal limit and ₹200 budget eats an unplanned samosa and sweet tea at 4pm.",
        profile=UserProfile(
            user_id="user_student_01",
            name="Aarav (Student)",
            diet_type=DietType.VEGETARIAN,
            daily_calorie_target=1800.0,
            daily_protein_target_g=60.0,
            daily_carbs_target_g=230.0,
            daily_fat_target_g=50.0,
            daily_budget_inr=200.0,
            max_prep_time_minutes=25,
            health_goal=HealthGoal.WEIGHT_LOSS
        ),
        logged_food_texts=[
            {"text": "1 fried vegetable samosa and 1 cutting masala chai", "meal_type": "snack", "logged_at": "16:30", "is_unplanned": True}
        ],
        disruptions=[
            DisruptionEvent(
                type="unplanned_meal",
                description="Had 1 samosa and cutting chai during group study.",
                data={"meal": "snack"}
            )
        ],
        expected_hard_constraints={
            "max_calories": 1950.0,
            "min_calories": 1400.0,
            "diet": "vegetarian",
            "max_cost": 210.0
        }
    ),
    BenchmarkScenario(
        id="scenario_02_missing_paneer_time_crunch",
        title="Working Professional: Missing Paneer & 15-Min Dinner Limit",
        description="Busy professional comes home late, finds fridge has no paneer and needs dinner ready in <= 15 mins without breaking vegetarian macros.",
        profile=UserProfile(
            user_id="user_pro_02",
            name="Pooja (Software Engineer)",
            diet_type=DietType.VEGETARIAN,
            daily_calorie_target=1700.0,
            daily_protein_target_g=65.0,
            daily_budget_inr=300.0,
            max_prep_time_minutes=30,
            health_goal=HealthGoal.WEIGHT_LOSS
        ),
        logged_food_texts=[
            {"text": "1 plate vegetable poha and 1 glass buttermilk", "meal_type": "breakfast", "logged_at": "09:00", "is_unplanned": False},
            {"text": "1 bowl toor dal, 2 rotis, and mixed veg curry", "meal_type": "lunch", "logged_at": "13:30", "is_unplanned": False}
        ],
        disruptions=[
            DisruptionEvent(
                type="missing_ingredient",
                description="Ran out of paneer in refrigerator.",
                data={"unavailable": ["paneer"]}
            ),
            DisruptionEvent(
                type="time_crunch",
                description="Only 15 minutes available to cook dinner.",
                data={"max_prep_time_minutes": 15}
            )
        ],
        expected_hard_constraints={
            "max_prep_time": 15,
            "diet": "vegetarian",
            "forbidden_ingredients": ["paneer"]
        }
    ),
    BenchmarkScenario(
        id="scenario_03_strict_jain_lunch",
        title="Strict Jain Consumer: Zero Root Vegetables & No Onion/Garlic",
        description="Strict Jain follower requiring verification that neither initial nor adapted meals contain potato, garlic, onion or root crops.",
        profile=UserProfile(
            user_id="user_jain_03",
            name="Bhavik (Jain Business Owner)",
            diet_type=DietType.JAIN,
            daily_calorie_target=1900.0,
            daily_protein_target_g=60.0,
            daily_budget_inr=250.0,
            max_prep_time_minutes=25,
            excluded_ingredients=["onion", "garlic", "potato"],
            health_goal=HealthGoal.HEALTHY_EATING
        ),
        logged_food_texts=[
            {"text": "2 idlis and 1 glass warm milk", "meal_type": "breakfast", "logged_at": "08:30", "is_unplanned": False}
        ],
        disruptions=[
            DisruptionEvent(
                type="missing_ingredient",
                description="Curd finished at home.",
                data={"unavailable": ["curd"]}
            )
        ],
        expected_hard_constraints={
            "diet": "jain",
            "no_root_veg": True
        }
    ),
    BenchmarkScenario(
        id="scenario_04_gym_eggetarian_heavy_biryani",
        title="High-Protein Eggetarian: Heavy Restaurant Biryani Lunch",
        description="Active fitness consumer logs an unplanned restaurant veg biryani lunch (550+ kcal) and needs dinner adjusted to hit 85g daily protein target.",
        profile=UserProfile(
            user_id="user_fit_04",
            name="Vikram (Gym Enthusiast)",
            diet_type=DietType.EGGETARIAN,
            daily_calorie_target=2200.0,
            daily_protein_target_g=85.0,
            daily_budget_inr=350.0,
            max_prep_time_minutes=20,
            health_goal=HealthGoal.MUSCLE_GAIN
        ),
        logged_food_texts=[
            {"text": "2 boiled eggs and 2 whole wheat rotis", "meal_type": "breakfast", "logged_at": "08:00", "is_unplanned": False},
            {"text": "1 plate restaurant vegetable dum biryani", "meal_type": "lunch", "logged_at": "14:00", "is_unplanned": True}
        ],
        disruptions=[
            DisruptionEvent(
                type="unplanned_meal",
                description="Client team lunch at biryani restaurant.",
                data={"meal": "lunch"}
            )
        ],
        expected_hard_constraints={
            "min_protein": 75.0,
            "diet": "eggetarian"
        }
    ),
    BenchmarkScenario(
        id="scenario_05_vegan_allergy_budget_crunch",
        title="Vegan with Peanut & Dairy Allergy on Strict Budget",
        description="Vegan consumer with strict allergies faces ₹50 daily budget cut and requires zero allergens and zero animal products.",
        profile=UserProfile(
            user_id="user_vegan_05",
            name="Ananya (Environmental Researcher)",
            diet_type=DietType.VEGAN,
            daily_calorie_target=1750.0,
            daily_protein_target_g=55.0,
            daily_budget_inr=180.0,
            allergies=["dairy", "peanuts"],
            max_prep_time_minutes=20,
            health_goal=HealthGoal.HEALTHY_EATING
        ),
        logged_food_texts=[
            {"text": "1 bowl oats porridge with water and pinch salt", "meal_type": "breakfast", "logged_at": "08:30", "is_unplanned": False}
        ],
        disruptions=[
            DisruptionEvent(
                type="budget_cut",
                description="Daily budget reduced to ₹150.",
                data={"cost_reduction_inr": 30.0}
            )
        ],
        expected_hard_constraints={
            "diet": "vegan",
            "forbidden_allergens": ["dairy", "peanuts"],
            "max_cost": 180.0
        }
    )
]
