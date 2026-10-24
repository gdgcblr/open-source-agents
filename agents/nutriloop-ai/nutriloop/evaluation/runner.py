"""
Benchmark Evaluation Runner.
Executes 4-way baseline comparison across held-out scenarios and computes rigorous metrics:
- Nutrient Calculation Error (%)
- Constraint Satisfaction (%)
- Adaptation Success (%)
- Unsupported Claims Count
- Cost Adherence (MAE)
"""

import sys
import pandas as pd
from typing import Dict, List, Any
from nutriloop.evaluation.benchmark import BENCHMARK_SCENARIOS
from nutriloop.evaluation.baselines import (
    StaticPlannerBaseline,
    StandaloneLLMBaseline,
    HeuristicConstraintBaseline,
    NutriLoopSystemWrapper
)


def run_evaluation_benchmark() -> pd.DataFrame:
    """Run full benchmark suite across all scenarios and return comparison DataFrame."""
    systems = [
        StaticPlannerBaseline(),
        StandaloneLLMBaseline(),
        HeuristicConstraintBaseline(),
        NutriLoopSystemWrapper()
    ]

    all_records: List[Dict[str, Any]] = []

    for system in systems:
        system_name = system.name
        arithmetic_errors = []
        constraint_satisfactions = []
        adaptation_successes = []
        unsupported_claims = []
        cost_maes = []

        for scenario in BENCHMARK_SCENARIOS:
            result = system.run(scenario)
            arithmetic_errors.append(result["arithmetic_error_pct"])
            constraint_satisfactions.append(result["constraint_satisfaction_pct"])
            adaptation_successes.append(result["adaptation_success_pct"])
            unsupported_claims.append(result["unsupported_claims_count"])
            cost_maes.append(result["cost_adherence_mae"])

        avg_arithmetic = sum(arithmetic_errors) / len(arithmetic_errors)
        avg_constraint = sum(constraint_satisfactions) / len(constraint_satisfactions)
        avg_adaptation = sum(adaptation_successes) / len(adaptation_successes)
        total_unsupported = sum(unsupported_claims)
        avg_cost_mae = sum(cost_maes) / len(cost_maes)

        all_records.append({
            "System Architecture": system_name,
            "Nutrient Arithmetic Error (%)": round(avg_arithmetic, 2),
            "Constraint Satisfaction (%)": round(avg_constraint, 1),
            "Adaptation Success Rate (%)": round(avg_adaptation, 1),
            "Unsupported Claims (Count)": total_unsupported,
            "Cost Adherence MAE (₹)": round(avg_cost_mae, 1)
        })

    df = pd.DataFrame(all_records)
    return df


def print_benchmark_report():
    """Print formatted markdown benchmark report for command line and README."""
    print("=" * 80)
    print("NutriLoop AI: Multi-Agent Benchmark Evaluation Report")
    print(f"Total Scenarios Evaluated: {len(BENCHMARK_SCENARIOS)}")
    print("=" * 80)
    df = run_evaluation_benchmark()
    try:
        print("\n" + df.to_markdown(index=False) + "\n")
    except Exception:
        print("\n" + df.to_string(index=False) + "\n")
    print("=" * 80)


if __name__ == "__main__":
    print_benchmark_report()
