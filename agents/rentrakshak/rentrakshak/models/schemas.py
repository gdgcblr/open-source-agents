from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class RiskCategory(str, Enum):
    LOW = "low_concern"
    NEEDS_VERIFICATION = "needs_verification"
    HIGH = "high_concern"
    CRITICAL = "critical_warning"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RedFlagFinding(BaseModel):
    rule_id: str
    severity: Severity
    evidence_excerpt: str
    explanation: str
    recommended_next_step: str


class ExtractedProperty(BaseModel):
    locality: str | None = None
    monthly_rent_inr: int | None = None
    deposit_inr: int | None = None
    bhk: str | None = None
    furnishing: str | None = None
    maintenance_inr: int | None = None
    property_type: str | None = None
    raw_notes: list[str] = Field(default_factory=list)


class RentEstimateResult(BaseModel):
    locality: str
    bhk: str | None
    furnishing: str | None
    property_type: str | None
    comparable_count: int
    rent_min_inr: int | None
    rent_median_inr: int | None
    rent_max_inr: int | None
    data_classification: str
    newest_observation_date: str | None
    oldest_observation_date: str | None
    methodology: str
    limitations: list[str]
    sufficient_data: bool


class ChecklistItemStatus(str, Enum):
    NOT_CHECKED = "not_checked"
    NEEDS_CLARIFICATION = "needs_clarification"
    EVIDENCE_SUPPLIED = "evidence_supplied"
    USER_VERIFIED = "user_verified"


class ChecklistItem(BaseModel):
    item_id: str
    title: str
    description: str
    category: Literal["legal", "official_guidance", "practical_recommendation"]
    status: ChecklistItemStatus = ChecklistItemStatus.NOT_CHECKED
    source_title: str | None = None
    source_url: str | None = None
    source_section: str | None = None
    date_checked: str | None = None


class LegalSourceRef(BaseModel):
    title: str
    url: str
    section: str | None = None
    date_checked: str
    scope: str
    explanation: str


class SafetyReport(BaseModel):
    property: ExtractedProperty
    missing_or_contradictory: list[str]
    risk_category: RiskCategory
    risk_reasoning: str
    findings: list[RedFlagFinding]
    verification_actions: list[str]
    rent_estimate: RentEstimateResult | None = None
    deposit_assessment: dict[str, Any] | None = None
    checklist_highlights: list[str] = Field(default_factory=list)
    questions_to_ask: list[str] = Field(default_factory=list)
    legal_sources: list[LegalSourceRef] = Field(default_factory=list)
    community_summary: dict[str, Any] | None = None
    limitations: list[str] = Field(default_factory=list)
    guardrail_notes: list[str] = Field(default_factory=list)


ExperienceSentiment = Literal["positive", "neutral", "negative"]
VacatingStatus = Literal[
    "draft", "pending_review", "active", "filled", "withdrawn", "expired"
]


class AnonymousExperienceInput(BaseModel):
    locality: str
    property_type: str
    rent_band: str | None = None
    category: str
    sentiment: ExperienceSentiment
    experience_text: str
    move_period: str | None = None
    rating_maintenance: int | None = Field(None, ge=1, le=5)
    rating_communication: int | None = Field(None, ge=1, le=5)

    @field_validator("experience_text")
    @classmethod
    def text_length(cls, v: str) -> str:
        if len(v.strip()) < 20:
            raise ValueError("experience_text must be at least 20 characters")
        if len(v) > 5000:
            raise ValueError("experience_text too long (max 5000)")
        return v.strip()


class VacatingPostInput(BaseModel):
    locality: str
    property_type: str
    room_type: str
    monthly_rent_inr: int = Field(..., gt=0)
    deposit_inr: int | None = Field(None, ge=0)
    availability_date: date
    furnishing: str | None = None
    maintenance_inr: int | None = Field(None, ge=0)
    post_kind: Literal["room_takeover", "roommate_replacement", "availability_lead"]
    description: str
    viewing_windows: str | None = None
    contact_method: str
    owner_permission_ack: bool = False

    @field_validator("description")
    @classmethod
    def desc_len(cls, v: str) -> str:
        if len(v.strip()) < 15:
            raise ValueError("description too short")
        if len(v) > 3000:
            raise ValueError("description too long")
        return v.strip()
