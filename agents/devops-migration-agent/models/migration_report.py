"""Models for migration reports, action mappings, and validation results."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from models.risk_model import RiskLevel


class ActionMappingStatus(str, Enum):
    """Classification of an action's migration support."""

    DIRECT = "direct"
    PARTIAL = "partial"
    MANUAL_MIGRATION = "manual_migration"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class ActionMappingResult(BaseModel):
    """Result of mapping a single GitHub Action to an Azure DevOps equivalent."""

    action_name: str
    action_version: str | None = None
    status: ActionMappingStatus
    ado_task: str | None = None
    ado_inputs: dict[str, Any] = Field(default_factory=dict)
    manual_steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    explanation: str = ""


class SecretReference(BaseModel):
    """Detected reference to a workflow secret."""

    secret_name: str
    source_job: str
    source_step: str
    recommended_ado_variable: str
    is_redacted: bool = True
    vault_reference: str | None = None


class ValidationResult(BaseModel):
    """Structural and semantic validation results."""

    is_valid: bool
    validation_type: str = "Azure Pipelines Structural Validation"
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    structural_checks: dict[str, bool] = Field(default_factory=dict)


class TerraformAnalysisResult(BaseModel):
    """Static analysis results for Terraform configuration."""

    has_terraform: bool = False
    file_count: int = 0
    providers: list[str] = Field(default_factory=list)
    backend_type: str | None = None
    resources_count: int = 0
    modules_count: int = 0
    service_connections_needed: list[str] = Field(default_factory=list)
    ci_apply_risk: bool = False
    findings: list[str] = Field(default_factory=list)


class MigrationSummary(BaseModel):
    """High-level summary of the workflow migration."""

    workflow_name: str
    source_file: str
    jobs_count: int
    steps_count: int
    direct_mappings_count: int
    partial_mappings_count: int
    manual_mappings_count: int
    unsupported_count: int
    unknown_count: int
    secrets_count: int
    risk_score: int
    risk_level: RiskLevel
    has_terraform: bool
    estimated_effort_hours: float
    status: str = "COMPLETED"
    generated_at: str = ""
