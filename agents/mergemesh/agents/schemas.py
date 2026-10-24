"""Pydantic schemas for validating structured AI explanations."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AIExplanationSchema(BaseModel):
    """Validated structured output expected from the MergeMesh ADK explainer agent."""

    summary: str = Field(
        ...,
        min_length=10,
        description="1. Summary: What changed across the provider and consumer repositories.",
    )
    compatibility_assessment: str = Field(
        default="",
        description="2. Compatibility assessment: What may break (or why the change is compatible) and why.",
    )
    why_it_matters: str = Field(
        ...,
        min_length=10,
        description="4. Impact: Which consumers, functions, or runtime code paths are affected.",
    )
    observed_facts: list[str] = Field(
        default_factory=list,
        description="3. Evidence: Supplied deterministic facts (contract fields, AST lines, executed tests) supporting the assessment.",
    )
    hypotheses: list[str] = Field(
        default_factory=list,
        description="5b. Uncertainty / Inferred risks: Candidate mappings or assumptions clearly separated from facts.",
    )
    severity_label: Literal["critical", "high", "medium", "low", "none"] = Field(
        default="high",
        description="5a. Severity level of the cross-repository compatibility risk.",
    )
    confidence_label: Literal["high", "medium", "low"] = Field(
        default="high",
        description="5a. Confidence level in the explanation.",
    )
    suggested_fix_options: list[str] = Field(
        default_factory=list,
        min_length=1,
        description="6a. Remediation: Concrete context-specific fix options for consumer and provider repositories.",
    )
    remediation_tradeoffs: str = Field(
        default="",
        description="6b. Trade-offs between updating the consumer vs. preserving backward compatibility in the provider.",
    )
    verification_plan: list[str] = Field(
        default_factory=list,
        description="7. Verification plan: Specific tests or checks to run to validate the proposed fix.",
    )
    suggested_test: str | None = Field(
        default=None,
        description="7b. Suggested targeted integration assertion or test snippet (as text only).",
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Explicit caveats, scope boundaries, and any missing evidence.",
    )

    @field_validator("severity_label", mode="before")
    @classmethod
    def _normalize_severity(cls, value: object) -> str:
        if isinstance(value, str):
            norm = value.strip().lower()
            if norm in {"critical", "high", "medium", "low", "none"}:
                return norm
        return "high"

    @field_validator("confidence_label", mode="before")
    @classmethod
    def _normalize_confidence(cls, value: object) -> str:
        if isinstance(value, str):
            norm = value.strip().lower()
            if norm in {"high", "medium", "low"}:
                return norm
        return "high"
