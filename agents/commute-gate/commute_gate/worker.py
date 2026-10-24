from __future__ import annotations

from commute_gate.agent import CommuteAgent
from commute_gate.config import load_settings
from commute_gate.models import CommuteSlots, WorkerStep


def run_worker_step(slots: CommuteSlots, *, faithful: bool = True) -> WorkerStep:
    """Compatibility wrapper used by older scripts; prefer CommuteAgent."""
    run = CommuteAgent(load_settings()).run(
        "worker-step",
        slots=slots,
        faithful=faithful,
        summarize_with_llm=False,
    )
    if run.step:
        return run.step
    return WorkerStep(
        proposed_action="get_routes",
        tool_name="get_routes",
        tool_args={},
        tool_result=None,
        agent_summary="Escalated before routing.",
        tool_error="gate_escalate",
    )
