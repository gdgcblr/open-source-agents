"""
Data models and Pydantic schemas for NutriLoop AI.
Ensures rigorous typing, validation, and serialization across agents.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator


class DietType(str, Enum):
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    EGGETARIAN = "eggetarian"
    NON_VEGETARIAN = "non_vegetarian"
    JAIN = "jain"


class HealthGoal(str, Enum):
    WEIGHT_LOSS = "weight_loss"
    MUSCLE_GAIN = "muscle_gain"
    MAINTENANCE = "maintenance"
    HEALTHY_EATING = "healthy_eating"


class Macronutrients(BaseModel):
    """Nutritional values typically normalized per 100g."""
    calories: float = Field(..., ge=0, description="Energy in kcal")
    protein_g: float = Field(..., ge=0, description="Protein in grams")
    carbs_g: float = Field(..., ge=0, description="Carbohydrates in grams")
    fat_g: float = Field(..., ge=0, description="Total fat in grams")
    fiber_g: float = Field(default=0.0, ge=0, description="Dietary fiber in grams")


class FoodItem(BaseModel):
    """Reference food record sourced from food composition tables (e.g. IFCT 2017)."""
    id: str
    name: str
    hindi_name: Optional[str] = None
    category: str  # e.g., grains, lentils, dairy, vegetables, snacks, proteins, fruits
    diet_type: DietType
    per_100g: Macronutrients
    default_portion_g: float = Field(default=100.0, gt=0)
    portion_description: str  # e.g., "1 bowl (150g)", "2 rotis (60g)"
    estimated_cost_inr: float = Field(default=20.0, ge=0)
    prep_time_minutes: int = Field(default=15, ge=0)
    allergens: List[str] = Field(default_factory=list)
    glycemic_index: str = Field(default="medium")  # low, medium, high
    is_jain_friendly: bool = Field(default=True)
    source: str = Field(default="ICMR-NIN IFCT 2017 & Standard Sourced Records")


class MealItem(BaseModel):
    """Specific portion of a food item inside a planned or consumed meal."""
    food_item_id: str
    name: str
    portion_g: float = Field(..., gt=0)
    portion_desc: str
    calories: float = Field(..., ge=0)
    protein_g: float = Field(..., ge=0)
    carbs_g: float = Field(..., ge=0)
    fat_g: float = Field(..., ge=0)
    fiber_g: float = Field(default=0.0, ge=0)
    cost_inr: float = Field(default=0.0, ge=0)


class Meal(BaseModel):
    """A single meal (e.g. breakfast, lunch, snack, dinner) with deterministic sums."""
    meal_type: str  # breakfast, lunch, snack, dinner
    items: List[MealItem] = Field(default_factory=list)
    total_calories: float = 0.0
    total_protein_g: float = 0.0
    total_carbs_g: float = 0.0
    total_fat_g: float = 0.0
    total_fiber_g: float = 0.0
    total_cost_inr: float = 0.0
    prep_time_minutes: int = 0

    @model_validator(mode="after")
    def calculate_totals(self) -> "Meal":
        """Deterministic calculation of meal totals from items."""
        if self.items:
            self.total_calories = round(sum(i.calories for i in self.items), 1)
            self.total_protein_g = round(sum(i.protein_g for i in self.items), 1)
            self.total_carbs_g = round(sum(i.carbs_g for i in self.items), 1)
            self.total_fat_g = round(sum(i.fat_g for i in self.items), 1)
            self.total_fiber_g = round(sum(i.fiber_g for i in self.items), 1)
            self.total_cost_inr = round(sum(i.cost_inr for i in self.items), 1)
            # Meal prep time is usually max of parallel preps or sum of active cooking
            self.prep_time_minutes = max((getattr(i, 'prep_time_minutes', 15) for i in self.items), default=15)
        return self


class DailyMealPlan(BaseModel):
    """Complete daily schedule consisting of all meals and verified totals."""
    plan_id: str
    day: str = "Today"
    meals: List[Meal] = Field(default_factory=list)
    total_calories: float = 0.0
    total_protein_g: float = 0.0
    total_carbs_g: float = 0.0
    total_fat_g: float = 0.0
    total_fiber_g: float = 0.0
    total_cost_inr: float = 0.0
    notes: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def calculate_plan_totals(self) -> "DailyMealPlan":
        """Deterministic aggregation across all meals in the day."""
        if self.meals:
            self.total_calories = round(sum(m.total_calories for m in self.meals), 1)
            self.total_protein_g = round(sum(m.total_protein_g for m in self.meals), 1)
            self.total_carbs_g = round(sum(m.total_carbs_g for m in self.meals), 1)
            self.total_fat_g = round(sum(m.total_fat_g for m in self.meals), 1)
            self.total_fiber_g = round(sum(m.total_fiber_g for m in self.meals), 1)
            self.total_cost_inr = round(sum(m.total_cost_inr for m in self.meals), 1)
        return self


class UserProfile(BaseModel):
    """Consumer profile with goals, dietary bounds, budget, and pantry context."""
    user_id: str = "user_default"
    name: str = "Everyday Consumer"
    diet_type: DietType = DietType.VEGETARIAN
    daily_calorie_target: float = Field(default=2000.0, gt=800, lt=5000)
    daily_protein_target_g: float = Field(default=65.0, ge=20)
    daily_carbs_target_g: float = Field(default=250.0, ge=20)
    daily_fat_target_g: float = Field(default=55.0, ge=10)
    daily_fiber_target_g: float = Field(default=25.0, ge=5)
    daily_budget_inr: float = Field(default=250.0, ge=50)
    max_prep_time_minutes: int = Field(default=30, ge=5)
    allergies: List[str] = Field(default_factory=list)  # e.g. ["dairy", "peanuts", "gluten"]
    excluded_ingredients: List[str] = Field(default_factory=list)
    available_pantry: List[str] = Field(default_factory=list)
    health_goal: HealthGoal = HealthGoal.WEIGHT_LOSS


class FoodLogEntry(BaseModel):
    """Record of real-life meals logged by the user."""
    meal_type: str  # breakfast, lunch, snack, dinner
    description: str
    consumed_items: List[MealItem] = Field(default_factory=list)
    total_calories: float = 0.0
    total_protein_g: float = 0.0
    total_carbs_g: float = 0.0
    total_fat_g: float = 0.0
    logged_at: str = "13:30"
    is_unplanned: bool = False
    notes: Optional[str] = None


class DisruptionEvent(BaseModel):
    """A real-life disturbance to the original meal plan."""
    type: str  # "unplanned_meal", "missing_ingredient", "time_crunch", "budget_cut"
    description: str
    data: Dict[str, Any] = Field(default_factory=dict)


class VerificationCheck(BaseModel):
    """Individual verification check result."""
    check_name: str
    passed: bool
    severity: str  # "critical", "warning", "info"
    details: str
    discrepancy_value: Optional[float] = None


class VerificationResult(BaseModel):
    """Complete deterministic audit report of a meal plan."""
    is_valid: bool
    checks: List[VerificationCheck] = Field(default_factory=list)
    arithmetic_error_percent: float = 0.0
    constraint_violations: List[str] = Field(default_factory=list)
    safety_flags: List[str] = Field(default_factory=list)
    verifier_notes: str = ""


class AgentActionTrace(BaseModel):
    """Structured log of agent activity, reasoning, and tool calls."""
    agent_name: str
    action: str
    reasoning: str
    timestamp: str
    details: Dict[str, Any] = Field(default_factory=dict)


class AdaptationResult(BaseModel):
    """End-to-end outcome of NutriLoop multi-agent adaptation loop."""
    original_plan: DailyMealPlan
    revised_plan: DailyMealPlan
    food_logs: List[FoodLogEntry] = Field(default_factory=list)
    disruptions: List[DisruptionEvent] = Field(default_factory=list)
    verification: VerificationResult
    traces: List[AgentActionTrace] = Field(default_factory=list)
    success: bool = True
    summary: str = ""
