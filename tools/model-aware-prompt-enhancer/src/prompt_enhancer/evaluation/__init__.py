"""Evaluation: offline deterministic benchmark and optional end-to-end A/B runs against a real model."""

from .dataset import Case, DatasetError, load_cases
from .runner import EvalReport, compare_to_baseline, run_offline

__all__ = ["Case", "DatasetError", "load_cases", "EvalReport", "run_offline", "compare_to_baseline"]
