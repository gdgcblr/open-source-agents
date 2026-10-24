"""Risk model definitions for DevOps migration assessment."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Categorized risk severity level."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskCategory(str, Enum):
    """Domain category for the risk factor."""

    SECURITY = "SECURITY"
    COMPATIBILITY = "COMPATIBILITY"
    OPERATIONAL = "OPERATIONAL"
    INFRASTRUCTURE = "INFRASTRUCTURE"


class RiskItem(BaseModel):
    """Individual identified migration risk."""

    id: str
    title: str
    description: str
    level: RiskLevel
    score_impact: int = Field(ge=0, le=100)
    category: RiskCategory
    remediation: str
    component: str = "general"
    blocker: bool = False


class RiskAssessment(BaseModel):
    """Aggregated risk assessment for the complete workflow migration."""

    overall_score: int = Field(ge=0, le=100)
    overall_level: RiskLevel
    items: list[RiskItem] = Field(default_factory=list)
    summary: str = ""
    blockers: list[str] = Field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for item in self.items if item.level == RiskLevel.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for item in self.items if item.level == RiskLevel.HIGH)

    @property
    def medium_count(self) -> int:
        return sum(1 for item in self.items if item.level == RiskLevel.MEDIUM)

    @property
    def low_count(self) -> int:
        return sum(1 for item in self.items if item.level == RiskLevel.LOW)

    @property
    def category_scores(self) -> dict[str, int]:
        breakdown: dict[str, int] = {}
        for item in self.items:
            cat = item.category.value
            breakdown[cat] = breakdown.get(cat, 0) + item.score_impact
        return breakdown
