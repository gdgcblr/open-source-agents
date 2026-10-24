from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from commute_gate.models import (
    CommuteSlots,
    DimensionScore,
    GateResult,
    WorkerStep,
)


@dataclass
class GateContext:
    slots: CommuteSlots
    end_goal: str
    user_request: str = ""
    memory: dict[str, str] = field(default_factory=dict)


@dataclass
class EvalContext:
    step: WorkerStep
    slots: CommuteSlots
    end_goal: str
    memory: dict[str, str] = field(default_factory=dict)


class GateCheck(Protocol):
    name: str
    description: str

    def run(self, ctx: GateContext) -> GateResult | None:
        """Return a result to apply, or None to pass through."""


class EvalCheck(Protocol):
    name: str
    description: str

    def run(self, ctx: EvalContext) -> DimensionScore | list[DimensionScore]:
        """Score one or more eval dimensions."""
