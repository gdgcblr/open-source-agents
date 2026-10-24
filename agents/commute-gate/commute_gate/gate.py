from __future__ import annotations

from commute_gate.models import CommuteSlots, GateResult
from commute_gate.policy.base import GateContext
from commute_gate.policy.registry import resolve_policy
from commute_gate.policy.runner import run_gates


def pre_action_gate(slots: CommuteSlots, end_goal: str, user_request: str = "") -> GateResult:
    """Run the enabled policy gates. App builders customize this via policy.yaml."""
    gates, _, _ = resolve_policy()
    return run_gates(gates, GateContext(slots=slots, end_goal=end_goal, user_request=user_request))
