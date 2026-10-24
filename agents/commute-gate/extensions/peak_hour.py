"""Example custom gate for app builders.

Enable it by uncommenting `peak_hour` under gates: in policy.yaml.
"""

from commute_gate.models import GateDecision, GateResult
from commute_gate.policy.base import GateContext


class PeakHourGate:
    name = "peak_hour"
    kind = "gate"
    description = "Warn when the trip lands in Bengaluru peak hours."

    def run(self, ctx: GateContext) -> GateResult | None:
        stamp = ctx.slots.arrive_by or ctx.slots.leave_by
        if not stamp:
            return None
        hour = int(stamp.split(":")[0])
        if hour < 8 or hour > 10:
            return None
        return GateResult(
            decision=GateDecision.ACT_WITH_ASSUMPTION,
            confidence=0.8,
            assumptions=[
                f"Trip time {stamp} is peak hour; durations may grow with traffic."
            ],
            rationale="Peak-hour assumption logged for the rider.",
            fired=[self.name],
        )
