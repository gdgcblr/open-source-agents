from __future__ import annotations

from dataclasses import asdict, dataclass

from commute_gate.config import Settings, load_settings
from commute_gate.llm.factory import get_llm_provider
from commute_gate.policy.base import EvalContext, GateContext
from commute_gate.policy.registry import PolicySpec, resolve_policy
from commute_gate.policy.runner import run_evals, run_gates
from commute_gate.models import (
    CommuteSlots,
    EvalReport,
    GateDecision,
    GateResult,
    RoutePlan,
    WorkerStep,
)
from commute_gate.parse import infer_goal, parse_slots_from_text, slots_from_llm_json
from commute_gate.places import resolve_place
from commute_gate.routing.factory import get_route_provider

SLOT_PROMPT = """Extract commute slots from the user message.
Return ONLY JSON with keys:
origin, destination, arrive_by, leave_by, constraints
Rules:
- Use Bengaluru place names when possible: Koramangala, Indiranagar, HSR Layout,
  Whitefield, MG Road, Kempegowda International Airport, Electronic City, Jayanagar,
  JP Nagar, BTM Layout, Marathahalli, Hebbal, Yeshwanthpur, Majestic, Silk Board,
  Banashankari, Rajajinagar, Malleshwaram, KR Puram, Manyata Tech Park, Domlur,
  Bellandur, Sarjapur, Kengeri, Shivajinagar, Lalbagh.
- arrive_by and leave_by must be 24h HH:MM or null.
- constraints is a list. Allowed flags: no_metro, no_bus, metro_only, accessibility.
- If a field is unknown, use null (or [] for constraints).
User message:
{message}
"""

SUMMARY_PROMPT = """Write a short commute plan for a rider in Bengaluru.
Use ONLY these facts. Do not invent routes, times, or line numbers.

FACTS:
{facts}

Write 2 sentences. Mention the exact line id, duration_min, departure, and arrival from FACTS.
Do not mention other line names.
"""


@dataclass
class AgentRun:
    user_request: str
    end_goal: str
    slots: CommuteSlots
    gate: GateResult
    step: WorkerStep | None
    report: EvalReport | None
    llm_used: str
    route_provider: str
    policy_source: str


class CommuteAgent:
    def __init__(
        self,
        settings: Settings | None = None,
        policy: PolicySpec | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.llm = get_llm_provider(self.settings)
        self.router = get_route_provider(self.settings)
        self.gates, self.evals, self.policy = resolve_policy(policy)

    def run(
        self,
        user_request: str,
        *,
        end_goal: str | None = None,
        slots: CommuteSlots | None = None,
        memory: dict[str, str] | None = None,
        faithful: bool = True,
        summarize_with_llm: bool | None = None,
    ) -> AgentRun:
        memory = memory or {}
        extracted = slots or self._extract_slots(user_request)
        extracted = _canonicalize(extracted)
        goal = end_goal or infer_goal(user_request, extracted)
        gate = run_gates(
            self.gates,
            GateContext(
                slots=extracted,
                end_goal=goal,
                user_request=user_request,
                memory=memory,
            ),
        )
        if summarize_with_llm is None:
            summarize_with_llm = slots is None

        if gate.decision == GateDecision.ESCALATE:
            return AgentRun(
                user_request=user_request,
                end_goal=goal,
                slots=extracted,
                gate=gate,
                step=None,
                report=None,
                llm_used=f"{self.llm.name}:{self.llm.model}",
                route_provider=self.router.name,
                policy_source=self.policy.source,
            )

        step = self._worker_step(
            extracted, faithful=faithful, summarize_with_llm=summarize_with_llm
        )
        report = run_evals(
            self.evals,
            EvalContext(step=step, slots=extracted, end_goal=goal, memory=memory),
        )
        return AgentRun(
            user_request=user_request,
            end_goal=goal,
            slots=extracted,
            gate=gate,
            step=step,
            report=report,
            llm_used=f"{self.llm.name}:{self.llm.model}",
            route_provider=self.router.name,
            policy_source=self.policy.source,
        )

    def _extract_slots(self, user_request: str) -> CommuteSlots:
        fallback = parse_slots_from_text(user_request)
        if self.llm.name == "none":
            return fallback
        try:
            payload = self.llm.generate_json(SLOT_PROMPT.format(message=user_request))
            llm_slots = slots_from_llm_json(payload)
        except (RuntimeError, ValueError):
            return fallback
        return CommuteSlots(
            origin=llm_slots.origin or fallback.origin,
            destination=llm_slots.destination or fallback.destination,
            arrive_by=llm_slots.arrive_by or fallback.arrive_by,
            leave_by=llm_slots.leave_by or fallback.leave_by,
            constraints=llm_slots.constraints or fallback.constraints,
        )

    def _worker_step(
        self,
        slots: CommuteSlots,
        *,
        faithful: bool,
        summarize_with_llm: bool,
    ) -> WorkerStep:
        tool_args = asdict(slots)
        try:
            plan = self.router.get_routes(slots)
        except ValueError as exc:
            return WorkerStep(
                proposed_action="get_routes",
                tool_name="get_routes",
                tool_args=tool_args,
                tool_result=None,
                agent_summary="No grounded route is available.",
                tool_error=str(exc),
            )
        summary = (
            _faithful_summary(plan)
            if faithful
            else _hallucinated_summary(plan)
        )
        if faithful and summarize_with_llm and self.llm.name != "none":
            try:
                summary = self.llm.generate_text(
                    SUMMARY_PROMPT.format(facts=_facts(plan))
                )
            except RuntimeError:
                pass
        return WorkerStep(
            proposed_action="get_routes",
            tool_name="get_routes",
            tool_args=tool_args,
            tool_result=plan,
            agent_summary=summary,
        )


def _canonicalize(slots: CommuteSlots) -> CommuteSlots:
    origin = resolve_place(slots.origin)
    dest = resolve_place(slots.destination)
    return CommuteSlots(
        origin=origin["name"] if origin else slots.origin,
        destination=dest["name"] if dest else slots.destination,
        arrive_by=slots.arrive_by,
        leave_by=slots.leave_by,
        constraints=slots.constraints,
    )


def _facts(plan: RoutePlan) -> str:
    legs = "; ".join(
        f"{leg.mode} {leg.line} {leg.duration_min} min departing {leg.departure}"
        for leg in plan.legs
    )
    return (
        f"origin={plan.origin}; destination={plan.destination}; "
        f"legs={legs}; total_duration_min={plan.total_duration_min}; "
        f"arrival={plan.arrival}"
    )


def _faithful_summary(plan: RoutePlan) -> str:
    legs = ", ".join(
        f"{leg.mode} {leg.line} ({leg.duration_min} min, dep {leg.departure})"
        for leg in plan.legs
    )
    return (
        f"Take {legs}. Total travel time is {plan.total_duration_min} minutes; "
        f"estimated arrival {plan.arrival}."
    )


def _hallucinated_summary(plan: RoutePlan) -> str:
    fake_minutes = max(5, plan.total_duration_min // 2)
    return (
        f"Take bus Line 99 for about {fake_minutes} minutes. "
        f"You should arrive around 08:10 with no transfers."
    )
