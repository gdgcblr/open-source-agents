from __future__ import annotations

from commute_gate.models import GateDecision, GateResult
from commute_gate.places import resolve_place
from commute_gate.policy.base import GateCheck, GateContext

QUESTIONS = {
    "origin": "Where are you leaving from (starting address or neighborhood)?",
    "destination": "Where do you need to go (exact destination or landmark)?",
    "arrive_by_or_leave_by": "Do you need to arrive by a specific time, or leave after a specific time?",
}


class RequiredSlotsGate:
    name = "required_slots"
    description = "Escalate if origin, destination, or time window is missing."

    def run(self, ctx: GateContext) -> GateResult | None:
        missing = ctx.slots.missing_for_planning()
        if not missing:
            return None
        return GateResult(
            decision=GateDecision.ESCALATE,
            confidence=0.95,
            clarifying_questions=[QUESTIONS[key] for key in missing if key in QUESTIONS],
            rationale="Required commute slots are missing; asking the rider instead of guessing.",
            fired=[self.name],
        )


class KnownPlacesGate:
    name = "known_places"
    description = "Escalate if origin or destination is not a known mapped place."

    def run(self, ctx: GateContext) -> GateResult | None:
        questions: list[str] = []
        if ctx.slots.origin and not resolve_place(ctx.slots.origin):
            questions.append("Which mapped neighborhood are you leaving from?")
        if ctx.slots.destination and not resolve_place(ctx.slots.destination):
            questions.append("Which exact mapped place do you need — not a vague label?")
        if not questions:
            return None
        return GateResult(
            decision=GateDecision.ESCALATE,
            confidence=0.9,
            clarifying_questions=questions,
            rationale="Place names could not be grounded in the local place registry.",
            fired=[self.name],
        )


class VaguePlaceGate:
    name = "vague_place"
    description = "Act with assumption if destination is a generic label (airport, office, home)."

    def run(self, ctx: GateContext) -> GateResult | None:
        dest = (ctx.slots.destination or "").strip().lower()
        if dest not in {"airport", "office", "work", "home", "station"}:
            return None
        return GateResult(
            decision=GateDecision.ACT_WITH_ASSUMPTION,
            confidence=0.75,
            assumptions=[
                f"Interpreted destination '{ctx.slots.destination}' as the nearest common match."
            ],
            rationale="Destination is generic; proceeding only with a logged assumption.",
            fired=[self.name],
        )


class AccessibilityGate:
    name = "accessibility"
    description = "Log an assumption if the goal mentions wheelchair access but no constraint was set."

    def run(self, ctx: GateContext) -> GateResult | None:
        if "wheelchair" not in ctx.end_goal.lower():
            return None
        if "accessibility" in ctx.slots.constraints:
            return None
        return GateResult(
            decision=GateDecision.ACT_WITH_ASSUMPTION,
            confidence=0.7,
            assumptions=["No accessibility constraint captured; defaulting to standard routes."],
            rationale="Goal mentions accessibility but slots do not.",
            fired=[self.name],
        )


BUILTIN_GATES: dict[str, GateCheck] = {
    check.name: check
    for check in (
        RequiredSlotsGate(),
        KnownPlacesGate(),
        VaguePlaceGate(),
        AccessibilityGate(),
    )
}
