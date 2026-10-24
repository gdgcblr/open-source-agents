"""Agent Reality Check package."""

from .evaluator import EvaluationResult, evaluate_response, run_scenario_suite
from .scenarios import Scenario, build_scenarios
from .providers import AgentProvider, MockAgentProvider, OllamaAgentProvider

__all__ = [
    "EvaluationResult",
    "Scenario",
    "build_scenarios",
    "evaluate_response",
    "run_scenario_suite",
    "AgentProvider",
    "MockAgentProvider",
    "OllamaAgentProvider",
]
