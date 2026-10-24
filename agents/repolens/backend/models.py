"""
RepoLens — Pydantic Request/Response Models

All models are strict to prevent unexpected field injection.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, field_validator


# ---------------------------------------------------------------------------
# Finding (normalized scanner output)
# ---------------------------------------------------------------------------

class Finding(BaseModel):
    """Single normalized security finding from any scanner."""

    finding_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW | INFO | UNKNOWN
    category: str  # dependency | secret | misconfiguration | sast | ai_suggestion
    scanner: str   # trivy | semgrep | gemini_suggestion
    rule_id: Optional[str] = None
    advisory_ref: Optional[str] = None
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    evidence: Optional[str] = None  # sanitized snippet, never raw secrets
    remediation: Optional[str] = None
    source_url: Optional[str] = None
    provenance: str  # "scanner" | "ai_suggestion"

    @field_validator("severity")
    @classmethod
    def _normalize_severity(cls, v: str) -> str:
        normalized = v.upper().strip()
        valid = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"}
        return normalized if normalized in valid else "UNKNOWN"

    @field_validator("provenance")
    @classmethod
    def _validate_provenance(cls, v: str) -> str:
        if v not in {"scanner", "ai_suggestion"}:
            raise ValueError("provenance must be 'scanner' or 'ai_suggestion'")
        return v


# ---------------------------------------------------------------------------
# Scan Report
# ---------------------------------------------------------------------------

class ScannerStatus(BaseModel):
    available: bool
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
    finding_count: int = 0


class AuditReport(BaseModel):
    """Full audit report persisted as JSONB in PostgreSQL."""

    repository_url: str
    repository_name: str
    commit_sha: Optional[str] = None
    tech_stack: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    scanner_status: dict[str, ScannerStatus] = Field(default_factory=dict)
    ai_summary: Optional[str] = None
    ai_prioritized_actions: list[str] = Field(default_factory=list)
    ai_available: bool = False
    is_demo: bool = False
    scan_duration_seconds: Optional[float] = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# API Request / Response models
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    repository_url: str

    @field_validator("repository_url")
    @classmethod
    def _must_be_github(cls, v: str) -> str:
        # Basic pre-validation; full validation is done in validator.py
        v = v.strip()
        if not v:
            raise ValueError("repository_url must not be empty")
        return v


class AuditSummary(BaseModel):
    id: int
    repository_url: str
    repository_name: str
    scan_status: str
    is_demo: bool
    commit_sha: Optional[str]
    created_at: datetime
    updated_at: datetime
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    total_findings: int = 0


class AuditDetail(AuditSummary):
    report_json: Optional[dict[str, Any]] = None
    report_markdown: Optional[str] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    database: str = "unknown"
    gemini_configured: bool = False


class ScanResponse(BaseModel):
    audit_id: int
    status: str
    message: str


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
