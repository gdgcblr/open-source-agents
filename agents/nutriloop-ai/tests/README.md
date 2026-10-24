# NutriLoop AI Test Suite (`tests/`)

This directory contains automated unit and integration tests verifying all components, mathematical operations, safety guardrails, and orchestration workflows.

---

## Test Organization

| Test File | Focus & Coverage |
| :--- | :--- |
| [`test_gemini_guardrails.py`](test_gemini_guardrails.py) | Google GenAI offline fallback, intake parsing guardrails, anti-starvation floor enforcement, and strict Jain/Vegan dietary boundary checks. |
| [`test_adaptive_replanner.py`](test_adaptive_replanner.py) | Dynamic dinner adaptation, unplanned snack handling, missing pantry substitutions (e.g., paneer substitutes). |
| [`test_nutrition_engine.py`](test_nutrition_engine.py) | Deterministic scaling arithmetic, household unit to gram conversions (katori, roti, plate), remaining allowance math. |
| [`test_orchestrator.py`](test_orchestrator.py) | End-to-end multi-agent execution loop, initial plan generation, and validation across all benchmark evaluation scenarios. |
| [`test_verifier.py`](test_verifier.py) | Independent verification engine rules: calorie summation error checks, allergen detection, and diet classification violations. |

---

## Running the Tests

Execute all tests from the project root:
```bash
pytest -v
```

Execute a specific test module:
```bash
pytest tests/test_gemini_guardrails.py -v
```
