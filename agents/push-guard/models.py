from enum import Enum
from typing import Optional
from pydantic import BaseModel


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Finding(BaseModel):
    agent: str
    severity: Severity
    title: str
    description: str
    line_ref: Optional[str] = None
    confidence: float  # 0.0 - 1.0


class ScanRequest(BaseModel):
    diff: str
    repo_name: Optional[str] = "unknown"


class ComplianceSummary(BaseModel):
    eu_cra: str
    nist_ssdf: str
    owasp_llm: str


class EvalScore(BaseModel):
    precision: float
    recall_estimate: float
    overall: float
    notes: str


class ScanResult(BaseModel):
    repo_name: str
    risk_score: int  # 0-100
    findings: list[Finding]
    compliance: ComplianceSummary
    eval_score: EvalScore
    summary: str
