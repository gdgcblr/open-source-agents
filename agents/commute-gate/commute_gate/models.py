from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GateDecision(str, Enum):
    ESCALATE = "ESCALATE"
    ACT = "ACT"
    ACT_WITH_ASSUMPTION = "ACT_WITH_ASSUMPTION"


class EvalVerdict(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class CommuteSlots:
    origin: str | None = None
    destination: str | None = None
    arrive_by: str | None = None
    leave_by: str | None = None
    constraints: list[str] = field(default_factory=list)

    def missing_for_planning(self) -> list[str]:
        missing: list[str] = []
        if not self.origin:
            missing.append("origin")
        if not self.destination:
            missing.append("destination")
        if not self.arrive_by and not self.leave_by:
            missing.append("arrive_by_or_leave_by")
        return missing


@dataclass
class GateResult:
    decision: GateDecision
    confidence: float
    clarifying_questions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    rationale: str = ""
    fired: list[str] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)


@dataclass
class RouteLeg:
    mode: str
    line: str
    duration_min: int
    departure: str


@dataclass
class RoutePlan:
    origin: str
    destination: str
    legs: list[RouteLeg]
    total_duration_min: int
    arrival: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkerStep:
    proposed_action: str
    tool_name: str
    tool_args: dict[str, Any]
    tool_result: RoutePlan | None
    agent_summary: str
    tool_error: str | None = None


@dataclass
class DimensionScore:
    name: str
    verdict: EvalVerdict
    score: float
    evidence: str


@dataclass
class EvalReport:
    overall: EvalVerdict
    dimensions: list[DimensionScore]
    recommended_action: GateDecision
    summary: str
    checks_run: list[str] = field(default_factory=list)
