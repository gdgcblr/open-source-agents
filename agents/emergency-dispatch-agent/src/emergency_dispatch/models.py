
from dataclasses import dataclass, field
from typing import Any, Literal


Severity = Literal["low", "moderate", "high", "critical"]


@dataclass(frozen=True)
class Incident:
    incident_id: str
    severity: Severity
    location: str
    required_capabilities: frozenset[str]
    required_hospital_capabilities: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Ambulance:
    ambulance_id: str
    location: str
    available: bool
    capabilities: frozenset[str]
    estimated_travel_minutes: float


@dataclass(frozen=True)
class Hospital:
    hospital_id: str
    name: str
    available_capabilities: frozenset[str]
    estimated_travel_minutes: float
    capacity_available: bool = True


@dataclass(frozen=True)
class AmbulanceCandidate:
    ambulance_id: str
    estimated_travel_minutes: float
    matched_capabilities: frozenset[str]


@dataclass(frozen=True)
class Exclusion:
    resource_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class DispatchRecommendation:
    status: Literal[
        "recommendation_available",
        "no_eligible_ambulance",
        "invalid_input",
        "insufficient_data",
    ]
    incident_id: str | None
    selected_ambulance: AmbulanceCandidate | None
    alternatives: tuple[AmbulanceCandidate, ...] = ()
    exclusions: tuple[Exclusion, ...] = ()
    explanation: str = ""
    human_approval_required: bool = True
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolResult:
    success: bool
    data: Any = None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass
class DispatchContext:
    """Shared state passed between orchestration steps."""

    incident: Incident | None = None
    ambulance_candidates: list[AmbulanceCandidate] = field(
        default_factory=list
    )
    exclusions: list[Exclusion] = field(default_factory=list)
    hospital_options: list[Hospital] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
