"""Data contracts for SecurePR AI."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class STRIDECategory(str, Enum):
    SPOOFING = "Spoofing"
    TAMPERING = "Tampering"
    REPUDIATION = "Repudiation"
    INFORMATION_DISCLOSURE = "Information Disclosure"
    DENIAL_OF_SERVICE = "Denial of Service"
    ELEVATION_OF_PRIVILEGE = "Elevation of Privilege"


class ExposureContext(str, Enum):
    PUBLIC = "PUBLIC"              # Directly internet-facing / unauthenticated
    INTERNAL = "INTERNAL"          # Requires valid internal network/VPN
    AUTHENTICATED = "AUTHENTICATED"# Requires standard user login
    LOCAL_ONLY = "LOCAL_ONLY"      # Test, sandbox, or build scripts
    UNKNOWN = "UNKNOWN"


class FindingCategory(str, Enum):
    SECRET = "SECRET"
    JWT_AUTH = "JWT_AUTH"
    API_AUTHORIZATION = "API_AUTHORIZATION"
    INPUT_VALIDATION = "INPUT_VALIDATION"
    DEPENDENCY = "DEPENDENCY"
    CONFIG = "CONFIG"


class Evidence(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    snippet: str
    sanitized: bool = True
    context_notes: Optional[str] = None


class Finding(BaseModel):
    id: str = Field(description="Unique stable ID, e.g., SEC-JWT-001")
    title: str
    category: FindingCategory
    stride: List[STRIDECategory]
    description: str
    scanner_name: str
    raw_severity: Severity
    evidence: List[Evidence]
    is_new_in_diff: bool = True
    cwe_id: Optional[str] = None
    owasp_api_category: Optional[str] = None
    remediation_hint: str


class AttackPathStep(BaseModel):
    step_number: int
    file_path: str
    action_or_state: str
    associated_finding_id: Optional[str] = None


class AttackPathHypothesis(BaseModel):
    id: str
    title: str
    summary: str
    stride: STRIDECategory
    steps: List[AttackPathStep]
    requires_validation: bool = True


class RiskScore(BaseModel):
    numeric_score: float = Field(ge=0.0, le=10.0, description="0.0 to 10.0 composite risk score")
    priority_level: Severity
    likelihood: float = Field(ge=0.0, le=1.0)
    impact: float = Field(ge=0.0, le=1.0)
    exposure_modifier: float
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class PrioritizedFinding(BaseModel):
    finding: Finding
    risk: RiskScore
    ai_explanation: Optional[str] = None
    ai_suggested_fix: Optional[str] = None


class ScanReport(BaseModel):
    repository_name: str
    target_commit_or_branch: str
    base_commit_or_branch: Optional[str] = None
    timestamp: str
    total_findings: int
    prioritized_findings: List[PrioritizedFinding]
    attack_path_hypotheses: List[AttackPathHypothesis]
    redacted_item_count: int
    passed_gate: bool
    summary: Dict[str, Any]
