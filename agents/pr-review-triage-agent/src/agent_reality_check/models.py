from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Status = Literal["PASS", "FAIL", "INCONCLUSIVE"]


@dataclass(frozen=True)
class Scenario:
    id: str
    category: str
    title: str
    prompt: str
    expectation: str
    response_rules: tuple[str, ...] = ()
    disallowed_phrases: tuple[str, ...] = ()
    expected_question_keywords: tuple[str, ...] = ()
    expected_confirmation_keywords: tuple[str, ...] = ()
    expected_missing_info_keywords: tuple[str, ...] = ()


@dataclass
class EvaluationResult:
    scenario_id: str
    category: str
    title: str
    status: Status
    reason: str
    observed_response: str
    pass_percentage: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status
        return data


@dataclass
class ScenarioReport:
    scenarios_total: int
    scenarios_passed: int
    scenarios_failed: int
    scenarios_inconclusive: int
    pass_percentage: float
    results: list[EvaluationResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenarios_total": self.scenarios_total,
            "scenarios_passed": self.scenarios_passed,
            "scenarios_failed": self.scenarios_failed,
            "scenarios_inconclusive": self.scenarios_inconclusive,
            "pass_percentage": self.pass_percentage,
            "results": [result.to_dict() for result in self.results],
        }
