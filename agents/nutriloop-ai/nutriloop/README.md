# NutriLoop AI Core Package (`nutriloop/`)

This package contains the core business logic, deterministic nutrition engines, verified food databases, data models, and multi-agent coordination system.

---

## Package Structure

```
nutriloop/
├── models.py              # Pydantic v2 schemas: UserProfile, Meal, DailyMealPlan, DisruptionEvent
├── database.py            # Verified food records grounded in ICMR-NIN IFCT 2017 & USDA
├── nutrition_engine.py    # Deterministic macro scaling, portion conversions, target computations
├── orchestrator.py        # Closed-loop orchestrator managing agent handoffs and repair cycles
├── agents/                # Specialized agent implementations (Planner, Analyzer, Replanner, Verifier)
└── evaluation/            # 4-way evaluation benchmark harness and comparative baselines
```

---

## Core Modules

### 1. [`models.py`](models.py)
Defines strongly-typed Pydantic v2 data models with automatic validator methods, positive numeric constraints, and serialization schemas for user profiles, disruptions, meals, verification audits, and inspectable action traces.

### 2. [`database.py`](database.py)
Houses 25+ curated everyday Indian and global food items with macronutrient breakdowns, glycemic indices, portion sizes, costs in ₹ INR, preparation times, and Jain/Vegan/Allergen suitability flags.

### 3. [`nutrition_engine.py`](nutrition_engine.py)
Calculates exact gram weights, macro nutrients, and meal costs with pure mathematical scaling. Guarantees 0.00% arithmetic divergence.

### 4. [`orchestrator.py`](orchestrator.py)
Coordinates the multi-agent pipeline from intake parsing to adaptive replanning, independent verification, and automated repair cycles.
