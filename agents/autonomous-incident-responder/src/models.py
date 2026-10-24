"""Data models and state representations for the Autonomous DevOps Incident Responder."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class IncidentState(str, Enum):
    """Explicit lifecycle states for DevOps incident response."""
    DETECTED = "DETECTED"
    INVESTIGATING = "INVESTIGATING"
    DIAGNOSED = "DIAGNOSED"
    REMEDIATING = "REMEDIATING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    FAILED = "FAILED"


class HealthState(str, Enum):
    """Service and dependency health statuses."""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


class SeverityLevel(str, Enum):
    """Standard incident severity classification."""
    SEV_1 = "SEV-1"  # Critical: full outage, severe business disruption, or critical security/integrity risk
    SEV_2 = "SEV-2"  # High: major degradation, critical function impaired, high error rate
    SEV_3 = "SEV-3"  # Moderate: limited impact, degraded non-critical dependency with workaround
    SEV_4 = "SEV-4"  # Low: minor error, nominal performance, cosmetic issue


class ResponsePriority(str, Enum):
    """Operational response urgency mapped from severity."""
    P1_CRITICAL_URGENT = "P1-CRITICAL-URGENT"  # Immediate page, executive escalation, 15m SLA
    P2_HIGH = "P2-HIGH"                        # High priority page, 30m SLA
    P3_MODERATE = "P3-MODERATE"                # Normal on-call queue, 2h SLA
    P4_LOW = "P4-LOW"                          # Next business day / low urgency


class SeverityAssessment(BaseModel):
    """Structured result of an impact-driven severity assessment."""
    severity: SeverityLevel
    priority: ResponsePriority
    reasons: List[str] = Field(default_factory=list)
    evidence_used: Dict[str, Any] = Field(default_factory=dict)
    missing_or_uncertain_evidence: List[str] = Field(default_factory=list)
    recommended_action: str = ""
    is_security_or_integrity_risk: bool = False
    requires_urgent_escalation: bool = False
    assessed_at: str = ""


class LogLevel(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogEntry(BaseModel):
    timestamp: str
    level: LogLevel
    service: str
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MetricSnapshot(BaseModel):
    timestamp: str
    error_rate: float
    latency_p95_ms: float
    latency_p50_ms: float
    request_volume_rpm: int
    cpu_utilization: float
    memory_utilization: float


class DependencyStatus(BaseModel):
    name: str
    status: HealthState
    latency_ms: float
    message: str
    last_checked: str


class DeploymentRecord(BaseModel):
    deployment_id: str
    timestamp: str
    author: str
    version: str
    status: str
    summary: str
    config_changes: Dict[str, Any] = Field(default_factory=dict)


class ToolCallRecord(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    success: bool = True
    error: Optional[str] = None
    timestamp: str = ""


class HealthCheckResult(BaseModel):
    service: str
    status: HealthState
    uptime_seconds: int
    restarts_count: int
    active_incidents: int
    message: str
    checks: Dict[str, bool] = Field(default_factory=dict)


class ConfigDiffResult(BaseModel):
    has_diff: bool
    changed_keys: List[str] = Field(default_factory=list)
    current_values: Dict[str, Any] = Field(default_factory=dict)
    known_good_values: Dict[str, Any] = Field(default_factory=dict)
    summary: str


class RemediationResult(BaseModel):
    action: str
    success: bool
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""


class VerificationResult(BaseModel):
    is_healthy: bool
    service_status: HealthState
    error_rate: float
    failing_dependencies: List[str] = Field(default_factory=list)
    has_config_drift: bool
    message: str


class IncidentRecord(BaseModel):
    """In-memory structured incident record tracking the entire lifecycle."""
    incident_id: str
    title: str
    service_name: str
    state: IncidentState = IncidentState.DETECTED
    symptoms: List[str] = Field(default_factory=list)
    observations: List[str] = Field(default_factory=list)
    hypotheses: List[str] = Field(default_factory=list)
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    action_results: List[RemediationResult] = Field(default_factory=list)
    verification_outcomes: List[VerificationResult] = Field(default_factory=list)
    root_cause: Optional[str] = None
    resolution_summary: Optional[str] = None
    escalation_reason: Optional[str] = None
    severity: Optional[SeverityLevel] = None
    severity_assessment: Optional[SeverityAssessment] = None
    severity_history: List[SeverityAssessment] = Field(default_factory=list)
    iterations: int = 0
    created_at: str = ""
    updated_at: str = ""

    def add_observation(self, note: str) -> None:
        if note not in self.observations:
            self.observations.append(note)

    def add_hypothesis(self, hypothesis: str) -> None:
        if hypothesis not in self.hypotheses:
            self.hypotheses.append(hypothesis)

    def record_tool_call(self, record: ToolCallRecord) -> None:
        self.tool_calls.append(record)
