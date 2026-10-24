from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class DriftSeverity(str, Enum):
    CRITICAL = "CRITICAL"   # Unauthenticated or unauthorized route exposure
    BREAKING = "BREAKING"   # Schema mismatch breaking consumers
    WARNING = "WARNING"     # Scope mismatches or undocumented endpoints
    INFO = "INFO"           # Cosmetic or documentation tags


class DriftType(str, Enum):
    # Schema Drift
    MISSING_ENDPOINT = "MISSING_ENDPOINT"
    EXTRA_ENDPOINT = "EXTRA_ENDPOINT"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    FIELD_REMOVED = "FIELD_REMOVED"
    FIELD_ADDED = "FIELD_ADDED"
    NULLABILITY_CHANGE = "NULLABILITY_CHANGE"
    STATUS_CODE_MISMATCH = "STATUS_CODE_MISMATCH"

    # Security & Policy Drift
    MISSING_AUTH_GUARD = "MISSING_AUTH_GUARD"
    MISSING_ROLE_SCOPE = "MISSING_ROLE_SCOPE"
    UNPROTECTED_SENSITIVE_DATA = "UNPROTECTED_SENSITIVE_DATA"
    EXCESSIVE_PERMISSIONS = "EXCESSIVE_PERMISSIONS"


class SecurityPolicy(BaseModel):
    endpoint: str = Field(description="HTTP Method and route path")
    expected_auth_schemes: List[str] = Field(default_factory=list, description="Schemes from spec (e.g., Bearer, OAuth2, ApiKey)")
    expected_scopes_or_roles: List[str] = Field(default_factory=list, description="Scopes or roles required in spec")
    code_auth_annotations: List[str] = Field(default_factory=list, description="Annotations in code (e.g., @PreAuthorize, @Secured)")
    is_compliant: bool = Field(description="True if code security matches or exceeds spec policy")


class ContractDriftItem(BaseModel):
    endpoint: str = Field(description="HTTP method and path, e.g., 'POST /api/v1/users'")
    drift_type: DriftType = Field(description="Classification of the contract or security difference")
    severity: DriftSeverity = Field(description="Impact level on downstream microservices or security posture")
    spec_state: str = Field(description="Expected behavior, schema, or security scheme in OpenAPI spec")
    code_state: str = Field(description="Actual behavior, schema, or security annotations in backend code")
    remediation: str = Field(description="Concrete action item to reconcile spec and implementation")


class ContractDriftReport(BaseModel):
    summary: str = Field(description="High-level assessment of API contract and security parity")
    has_breaking_changes: bool = Field(description="True if breaking contract or critical security issues exist")
    security_audit_passed: bool = Field(description="True if zero security policy drifts were detected")
    security_evaluations: List[SecurityPolicy] = Field(default_factory=list, description="Per-endpoint security posture assessment")
    drift_items: List[ContractDriftItem] = Field(description="List of detected drift occurrences")
    suggested_spec_patch: Optional[str] = Field(
        default=None,
        description="JSON/YAML snippet to patch OpenAPI spec"
    )
    suggested_security_patch: Optional[str] = Field(
        default=None,
        description="Java/TS/Python code snippet showing required security annotations or guards"
    )