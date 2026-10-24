from __future__ import annotations

import re

from commute_gate.models import DimensionScore, EvalVerdict
from commute_gate.policy.base import EvalCheck, EvalContext


def _minutes_in_text(text: str) -> set[int]:
    return {int(match) for match in re.findall(r"\b(\d{1,3})\s*(?:min|minutes|m)\b", text.lower())}


def _lines_in_text(text: str, known: set[str] | None = None) -> set[str]:
    found: set[str] = set()
    for line in known or set():
        if re.search(rf"\b{re.escape(line)}\b", text, flags=re.I):
            found.add(line.lower())
    for match in re.finditer(r"\b([A-Za-z]{0,4}\d{1,4}(?:-[A-Za-z0-9]+)?)\b", text):
        token = match.group(1)
        if token.isdigit():
            continue
        found.add(token.lower())
    for color in ("purple", "green", "yellow", "blue", "pink"):
        if re.search(rf"\b{color}\b", text, flags=re.I):
            found.add(color)
    return found


def _parse_hhmm(value: str) -> int | None:
    match = re.match(r"^(\d{1,2}):(\d{2})$", value.strip())
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


class ToolAvailableEval:
    name = "tool_available"
    description = "FAIL if the routing tool returned no result."

    def run(self, ctx: EvalContext) -> DimensionScore:
        if ctx.step.tool_error or ctx.step.tool_result is None:
            return DimensionScore(
                name=self.name,
                verdict=EvalVerdict.FAIL,
                score=0.0,
                evidence=f"Tool error: {ctx.step.tool_error or 'no result'}",
            )
        return DimensionScore(
            name=self.name,
            verdict=EvalVerdict.PASS,
            score=100.0,
            evidence="Routing tool returned a plan.",
        )


class ToolFaithfulnessEval:
    name = "tool_faithfulness"
    description = "FAIL if the written summary invents lines, minutes, or modes."

    def run(self, ctx: EvalContext) -> DimensionScore:
        plan = ctx.step.tool_result
        if plan is None:
            return DimensionScore(
                name=self.name,
                verdict=EvalVerdict.FAIL,
                score=0.0,
                evidence="No tool result to compare against.",
            )
        summary = ctx.step.agent_summary.lower()
        claimed_minutes = _minutes_in_text(ctx.step.agent_summary)
        true_minutes = {plan.total_duration_min} | {leg.duration_min for leg in plan.legs}
        minute_ok = not claimed_minutes or claimed_minutes.issubset(true_minutes)

        allowed_lines = {leg.line.lower() for leg in plan.legs}
        for alt in plan.raw.get("alternatives") or []:
            for line in alt.get("lines") or []:
                allowed_lines.add(str(line).lower())
        claimed_lines = _lines_in_text(ctx.step.agent_summary, known=allowed_lines)
        line_ok = not claimed_lines or claimed_lines.issubset(allowed_lines)

        modes_in_plan = {leg.mode.lower() for leg in plan.legs}
        for alt in plan.raw.get("alternatives") or []:
            if alt.get("mode"):
                modes_in_plan.add(str(alt["mode"]).lower())
        mode_claims = set(re.findall(r"\b(bus|metro|train|subway|walk)\b", summary))
        mode_ok = not mode_claims or mode_claims.issubset(modes_in_plan)

        ok = minute_ok and line_ok and mode_ok
        return DimensionScore(
            name=self.name,
            verdict=EvalVerdict.PASS if ok else EvalVerdict.FAIL,
            score=100.0 if ok else 25.0,
            evidence=(
                f"tool total={plan.total_duration_min}m, legs={[leg.line for leg in plan.legs]}; "
                f"summary minutes={sorted(claimed_minutes) or 'none'}, "
                f"lines={sorted(claimed_lines) or 'none'}"
            ),
        )


class MemoryConsistencyEval:
    name = "memory_consistency"
    description = "FAIL if the plan contradicts stored rider preferences."

    def run(self, ctx: EvalContext) -> DimensionScore:
        plan = ctx.step.tool_result
        modes = {leg.mode.lower() for leg in plan.legs} if plan else set()
        issues: list[str] = []
        if ctx.memory.get("no_metro") == "true" and "metro" in modes:
            issues.append("Plan includes metro but memory.no_metro=true")
        if (
            ctx.memory.get("origin")
            and ctx.slots.origin
            and ctx.memory["origin"].lower() != ctx.slots.origin.lower()
        ):
            issues.append("slots.origin contradicts memory.origin")
        return DimensionScore(
            name=self.name,
            verdict=EvalVerdict.PASS if not issues else EvalVerdict.FAIL,
            score=100.0 if not issues else 20.0,
            evidence="; ".join(issues) if issues else "No memory conflicts detected.",
        )


class GoalAlignmentEval:
    name = "goal_alignment"
    description = "WARN if planned arrival misses the arrive-by goal."

    def run(self, ctx: EvalContext) -> DimensionScore:
        plan = ctx.step.tool_result
        if not ctx.slots.arrive_by:
            return DimensionScore(
                name=self.name,
                verdict=EvalVerdict.PASS,
                score=100.0,
                evidence="No arrive-by constraint to verify.",
            )
        if plan is None:
            return DimensionScore(
                name=self.name,
                verdict=EvalVerdict.FAIL,
                score=0.0,
                evidence="No plan arrival to compare with the goal.",
            )
        target = _parse_hhmm(ctx.slots.arrive_by)
        actual = _parse_hhmm(plan.arrival)
        if target is None or actual is None:
            return DimensionScore(
                name=self.name,
                verdict=EvalVerdict.WARN,
                score=50.0,
                evidence="Could not parse arrive-by or planned arrival times.",
            )
        ok = actual <= target
        return DimensionScore(
            name=self.name,
            verdict=EvalVerdict.PASS if ok else EvalVerdict.WARN,
            score=100.0 if ok else 50.0,
            evidence=f"arrive_by={ctx.slots.arrive_by}, planned arrival={plan.arrival}",
        )


BUILTIN_EVALS: dict[str, EvalCheck] = {
    check.name: check
    for check in (
        ToolAvailableEval(),
        ToolFaithfulnessEval(),
        MemoryConsistencyEval(),
        GoalAlignmentEval(),
    )
}
