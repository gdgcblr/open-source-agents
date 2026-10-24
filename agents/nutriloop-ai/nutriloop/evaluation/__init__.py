"""
NutriLoop Evaluation and Benchmark Suite.
"""

from nutriloop.evaluation.benchmark import BENCHMARK_SCENARIOS, BenchmarkScenario
from nutriloop.evaluation.baselines import (
    StaticPlannerBaseline,
    StandaloneLLMBaseline,
    HeuristicConstraintBaseline,
    NutriLoopSystemWrapper
)
from nutriloop.evaluation.runner import run_evaluation_benchmark

__all__ = [
    "BENCHMARK_SCENARIOS",
    "BenchmarkScenario",
    "StaticPlannerBaseline",
    "StandaloneLLMBaseline",
    "HeuristicConstraintBaseline",
    "NutriLoopSystemWrapper",
    "run_evaluation_benchmark"
]
