# NutriLoop AI Evaluation & Benchmark Harness (`nutriloop/evaluation/`)

This directory contains the scientific evaluation framework and 4-way architectural benchmark comparing NutriLoop AI against baseline approaches across held-out consumer disruption scenarios.

---

## 4-Way Architectural Comparison

The benchmark evaluates 4 distinct architectures:

1. **Static Meal Planner**: Standard fixed meal plan with zero dynamic adaptation when reality disrupts the schedule.
2. **Standalone LLM (Ungrounded)**: Monolithic LLM prompt attempting to recalculate calories, portions, and diets without tools or deterministic checks.
3. **Heuristic Constraint Planner**: Rule-based system that scales meal sizes naively by a fixed percentage without ingredient substitution intelligence.
4. **NutriLoop AI (Multi-Agent)**: The full closed-loop multi-agent system combining Google GenAI reasoning with deterministic ICMR-NIN database grounding and an independent audit engine.

---

## Key Metrics Evaluated

| Metric | Target | Description |
| :--- | :---: | :--- |
| **Nutrient Arithmetic Error (%)** | **$< 1.0\%$** | Absolute divergence between meal sum and stated daily total calories. |
| **Constraint Satisfaction (%)** | **$100\%$** | Percentage of hard constraints satisfied (Jain, Vegan, Allergens, Prep Time). |
| **Adaptation Success Rate (%)** | **$\ge 90\%$** | Successful resolution of disruptions without crash starvation. |
| **Unsupported Claims (Count)** | **$0$** | Hallucinated nutrient numbers or ungrounded assertions. |
| **Cost Adherence MAE (₹)** | **Min** | Mean absolute error between actual cost and target budget. |

---

## How to Run the Benchmark

From the project root:
```bash
python main.py --benchmark
# or directly:
python -m nutriloop.evaluation.runner
```

---

## Files in this Directory

- [`benchmark.py`](benchmark.py): Standardized held-out evaluation scenarios reflecting diverse Indian diets (Vegetarian, Vegan, Jain, Eggetarian), economic constraints (₹180–₹250/day), and lifestyle disruptions.
- [`baselines.py`](baselines.py): Implementation wrappers for the 4 compared architectures.
- [`runner.py`](runner.py): Execution runner and automated Markdown/table reporting harness.
