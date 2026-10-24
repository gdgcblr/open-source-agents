from __future__ import annotations

from commute_gate.models import CommuteSlots, EvalReport, WorkerStep
from commute_gate.policy.base import EvalContext
from commute_gate.policy.evals import _lines_in_text, _minutes_in_text, _parse_hhmm
from commute_gate.policy.registry import resolve_policy
from commute_gate.policy.runner import run_evals


def evaluate_step(
    step: WorkerStep,
    slots: CommuteSlots,
    end_goal: str,
    memory: dict[str, str],
) -> EvalReport:
    """Run the enabled policy evals. App builders customize this via policy.yaml."""
    _, evals, _ = resolve_policy()
    return run_evals(
        evals,
        EvalContext(step=step, slots=slots, end_goal=end_goal, memory=memory),
    )


# Re-export helpers so older imports keep working.
__all__ = ["evaluate_step", "_lines_in_text", "_minutes_in_text", "_parse_hhmm"]
