"""
NutriLoop Multi-Agent Orchestrator.
Coordinates the specialized agents in a closed feedback loop with deterministic repair cycles.
State graph:
[User Context / Disruptions]
       │
       ▼
[Food Analyzer Agent]  <── (Parses logged intake & portions)
       │
       ▼
[Adaptive Replanner Agent] <────┐ (Repair Cycle on Audit Rejection)
       │                        │
       ▼                        │
[Verification Engine] ──────────┘
       │ (Audit Passed)
       ▼
[Verified Actionable Plan + Traces]
"""

from typing import List, Optional
from nutriloop.models import (
    UserProfile,
    DailyMealPlan,
    FoodLogEntry,
    DisruptionEvent,
    AdaptationResult,
    AgentActionTrace
)
from nutriloop.agents.food_analyzer import FoodAnalyzerAgent
from nutriloop.agents.planner import FeasibilityPlannerAgent
from nutriloop.agents.adaptive_replanner import AdaptiveReplannerAgent
from nutriloop.agents.verifier import IndependentVerificationEngine


class NutriLoopOrchestrator:
    """Manages multi-agent workflow, feedback loop, and verification enforcement."""

    def __init__(self):
        self.food_analyzer = FoodAnalyzerAgent()
        self.planner = FeasibilityPlannerAgent()
        self.replanner = AdaptiveReplannerAgent()
        self.verifier = IndependentVerificationEngine()

    def run_initial_plan(self, profile: UserProfile) -> AdaptationResult:
        """Generate and verify an initial baseline plan for a user profile."""
        all_traces: List[AgentActionTrace] = []

        # 1. Generate plan
        plan = self.planner.generate_plan(profile)
        all_traces.extend(self.planner.traces)

        # 2. Audit plan
        verification = self.verifier.verify_plan(plan, profile)
        all_traces.extend(self.verifier.traces)

        return AdaptationResult(
            original_plan=plan,
            revised_plan=plan,
            food_logs=[],
            disruptions=[],
            verification=verification,
            traces=all_traces,
            success=verification.is_valid,
            summary=f"Initial plan created: {plan.total_calories:.1f} kcal, {plan.total_protein_g:.1f}g protein. Verification: {'PASSED' if verification.is_valid else 'FAILED'}."
        )

    def adapt_to_disruptions(
        self,
        profile: UserProfile,
        current_plan: DailyMealPlan,
        raw_food_logs: List[dict],
        disruptions: List[DisruptionEvent],
        max_repair_cycles: int = 3
    ) -> AdaptationResult:
        """
        Execute full closed-loop adaptation:
        Intake parsing -> Adaptive replanning -> Deterministic verification -> Repair loop if required.
        """
        all_traces: List[AgentActionTrace] = []

        # Step 1: Parse and ground all food logs
        processed_logs: List[FoodLogEntry] = []
        for raw_log in raw_food_logs:
            entry = self.food_analyzer.analyze_food_log(
                text=raw_log.get("text", ""),
                meal_type=raw_log.get("meal_type", "lunch"),
                logged_at=raw_log.get("logged_at", "13:30"),
                is_unplanned=raw_log.get("is_unplanned", False)
            )
            processed_logs.append(entry)
        all_traces.extend(self.food_analyzer.traces)

        # Step 2: Adaptive Replanning with verification feedback loop
        repair_cycle = 0
        feedback_notes = None
        revised_plan = current_plan
        verification = None

        # Determine effective prep time limit from disruptions
        time_limit = profile.max_prep_time_minutes
        for d in disruptions:
            if d.type == "time_crunch" and "max_prep_time_minutes" in d.data:
                time_limit = min(time_limit, d.data["max_prep_time_minutes"])

        while repair_cycle <= max_repair_cycles:
            self.replanner.clear_traces()
            self.verifier.clear_traces()

            revised_plan = self.replanner.replan(
                current_plan=current_plan,
                profile=profile,
                food_logs=processed_logs,
                disruptions=disruptions,
                feedback_notes=feedback_notes
            )
            all_traces.extend(self.replanner.traces)

            # Audit the revised plan
            verification = self.verifier.verify_plan(revised_plan, profile, max_prep_time=time_limit)
            all_traces.extend(self.verifier.traces)

            if verification.is_valid:
                break

            # If failed, prepare feedback for next repair attempt
            repair_cycle += 1
            feedback_notes = f"Attempt {repair_cycle}: Verifier reported {len(verification.constraint_violations)} violation(s): {'; '.join(verification.constraint_violations[:2])}"

        success = verification.is_valid if verification else False
        summary = (
            f"Adaptation {'SUCCESS' if success else 'PARTIAL'}: "
            f"Original: {current_plan.total_calories:.1f} kcal -> "
            f"Adapted: {revised_plan.total_calories:.1f} kcal ({revised_plan.total_protein_g:.1f}g protein). "
            f"Arithmetic error: {verification.arithmetic_error_percent:.2f}%. "
            f"Constraint violations: {len(verification.constraint_violations)}."
        )

        return AdaptationResult(
            original_plan=current_plan,
            revised_plan=revised_plan,
            food_logs=processed_logs,
            disruptions=disruptions,
            verification=verification,
            traces=all_traces,
            success=success,
            summary=summary
        )
