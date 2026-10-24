"""Shared typed contracts."""
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Any
    requires_approval: bool = False
    allowed: bool = True


@dataclass(frozen=True)
class Decision:
    verdict: Literal["allow", "review", "block"]
    reason: str
    confidence: float = 1.0


@dataclass
class RunResult:
    answer: str
    steps: int
    tool_calls: int
    estimated_cost_usd: float
    blocked: bool = False
    warnings: list[str] = field(default_factory=list)
