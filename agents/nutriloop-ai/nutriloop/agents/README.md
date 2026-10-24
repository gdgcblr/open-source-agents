# NutriLoop AI Multi-Agent Subsystem (`nutriloop/agents/`)

This directory houses the specialized agent implementations that coordinate in a closed loop to provide adaptive, verified dietary guidance.

---

## Agent Roles & Architecture

```
                 ┌────────────────────────────────┐
                 │       FeasibilityPlanner       │
                 │   (Generates baseline plan)    │
                 └───────────────┬────────────────┘
                                 │
                                 ▼
┌──────────────────┐    ┌────────────────────────┐    ┌─────────────────────────┐
│ User Disruption  ├───►│   FoodAnalyzerAgent    ├───►│ AdaptiveReplannerAgent  │◄──┐
│ (Samosa, Chai)   │    │ (Gemini entity parsing)│    │ (Recalculates dinner)   │   │
└──────────────────┘    └────────────────────────┘    └────────────┬────────────┘   │ Repair
                                                                   │                │ Loop
                                                                   ▼                │ (Feedback)
                                                      ┌─────────────────────────┐   │
                                                      │ IndependentVerification │───┘
                                                      │ (Safety & math audit)   │
                                                      └────────────┬────────────┘
                                                                   │ (Passed)
                                                                   ▼
                                                      ┌─────────────────────────┐
                                                      │  Verified Revised Plan  │
                                                      └─────────────────────────┘
```

---

## Agents Overview

### 1. [`FeasibilityPlannerAgent`](planner.py)
- **Role**: Baseline meal plan generation.
- **Function**: Constructs an initial 4-meal daily schedule tailored to user calorie, protein, diet type (Vegetarian, Vegan, Jain, Eggetarian), and daily budget limits.

### 2. [`FoodAnalyzerAgent`](food_analyzer.py)
- **Role**: Dietary intake & portion estimator.
- **Function**: Ingests natural language food descriptions (e.g. *"1 fried vegetable samosa and 1 cutting masala chai"*).
- **Google GenAI / ADK Integration**: Uses Gemini 2.5 Flash to extract dish names and household portion units into structured JSON.
- **Guardrail**: Binds items strictly to ICMR-NIN IFCT tables; never permits LLM arithmetic hallucination.

### 3. [`AdaptiveReplannerAgent`](adaptive_replanner.py)
- **Role**: Closed-loop meal replanner.
- **Function**: Adapts upcoming meal slots (e.g. Dinner) when real-life disruptions occur (unplanned snacks, missing fridge ingredients, 15-minute cooking time crunch).
- **Google GenAI / ADK Integration**: Generates context-aware, empathetic nutrition coaching insights and recommends catalog-compliant dishes.
- **Guardrail**: Enforces minimum safe calorie floors ($\ge 250\text{ kcal}$ for dinner) to prevent punitive starvation.

### 4. [`IndependentVerificationEngine`](verifier.py)
- **Role**: Deterministic safety auditor.
- **Function**: Validates every candidate plan against 6 deterministic criteria:
  1. *Calorie Summation Error* ($< 1.0\%$)
  2. *Dietary Compatibility* (Jain, Vegan, Vegetarian constraints)
  3. *Allergen Safety* (Prohibits declared allergens)
  4. *Cooking Time Feasibility* (Respects prep bottlenecks)
  5. *Budget Compliance* (Enforces daily ₹ INR caps)
  6. *Anti-Starvation Guard* ($\ge 1000\text{ kcal}$ daily floor, $\ge 250\text{ kcal}$ dinner)
- **Repair Feedback**: Rejects invalid plans and supplies actionable feedback to the replanner.

### 5. [`BaseAgent`](base.py)
- **Role**: Foundational abstraction.
- **Function**: Manages Google GenAI client initialization (`get_gemini_client()`), model configurations, inspectable reasoning traces (`record_trace()`), and offline fallbacks.
