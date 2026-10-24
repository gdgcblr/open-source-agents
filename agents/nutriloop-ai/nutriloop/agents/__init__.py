"""
Multi-agent system modules for NutriLoop AI.
"""

from nutriloop.agents.base import BaseAgent
from nutriloop.agents.food_analyzer import FoodAnalyzerAgent
from nutriloop.agents.planner import FeasibilityPlannerAgent
from nutriloop.agents.adaptive_replanner import AdaptiveReplannerAgent
from nutriloop.agents.verifier import IndependentVerificationEngine

__all__ = [
    "BaseAgent",
    "FoodAnalyzerAgent",
    "FeasibilityPlannerAgent",
    "AdaptiveReplannerAgent",
    "IndependentVerificationEngine"
]
