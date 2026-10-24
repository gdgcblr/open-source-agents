from __future__ import annotations

from commute_gate.models import (
    DimensionScore,
    EvalReport,
    EvalVerdict,
    GateDecision,
    GateResult,
)
from commute_gate.policy.base import EvalCheck, EvalContext, GateCheck, GateContext


def run_gates(checks: list[GateCheck], ctx: GateContext) -> GateResult:
    questions: list[str] = []
    assumptions: list[str] = []
    fired: list[str] = []
    decision = GateDecision.ACT
    confidence = 0.9
    rationale = "All enabled gates passed; safe to call routing tools."

    for check in checks:
        result = check.run(ctx)
        if result is None:
            continue
        fired.extend(result.fired or [check.name])
        if result.decision == GateDecision.ESCALATE:
            result.checks_run = [item.name for item in checks]
            result.fired = fired
            return result
        if result.decision == GateDecision.ACT_WITH_ASSUMPTION:
            decision = GateDecision.ACT_WITH_ASSUMPTION
            confidence = min(confidence, result.confidence)
            questions.extend(result.clarifying_questions)
            assumptions.extend(result.assumptions)
            rationale = result.rationale or rationale

    return GateResult(
        decision=decision,
        confidence=confidence,
        clarifying_questions=questions,
        assumptions=assumptions,
        rationale=rationale,
        fired=fired,
        checks_run=[item.name for item in checks],
    )


def run_evals(checks: list[EvalCheck], ctx: EvalContext) -> EvalReport:
    dimensions: list[DimensionScore] = []
    for check in checks:
        result = check.run(ctx)
        if isinstance(result, list):
            dimensions.extend(result)
        else:
            dimensions.append(result)

    if any(dim.verdict == EvalVerdict.FAIL for dim in dimensions):
        overall = EvalVerdict.FAIL
        recommended = GateDecision.ESCALATE
        summary = (
            "An enabled eval failed. Do not show this plan to the user as-is; "
            "rewrite from tool JSON or escalate."
        )
    elif any(dim.verdict == EvalVerdict.WARN for dim in dimensions):
        overall = EvalVerdict.WARN
        recommended = GateDecision.ACT_WITH_ASSUMPTION
        summary = "Plan is mostly grounded but needs confirmation."
    else:
        overall = EvalVerdict.PASS
        recommended = GateDecision.ACT
        summary = "Enabled evals passed; the reply is safe to show."

    if ctx.end_goal:
        summary += f" End goal context: {ctx.end_goal}"

    return EvalReport(
        overall=overall,
        dimensions=dimensions,
        recommended_action=recommended,
        summary=summary,
        checks_run=[item.name for item in checks],
    )
