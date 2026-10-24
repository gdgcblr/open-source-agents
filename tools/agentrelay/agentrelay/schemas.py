"""Typed data models and validation schemas for AgentRelay."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

# Allowed enumerations
ALLOWED_SEVERITIES: Set[str] = {"critical", "high", "medium", "low", "info"}
ALLOWED_CONFIDENCES: Set[str] = {"low", "medium", "high"}
ALLOWED_SOURCE_TYPES: Set[str] = {
    "diff",
    "log",
    "metric",
    "trace",
    "deployment",
    "test",
    "manual",
}
ALLOWED_HYPOTHESIS_LIKELIHOODS: Set[str] = {"plausible", "possible", "unlikely"}


class ValidationError(ValueError):
    """Raised when data fails schema validation."""


@dataclass
class EvidenceRecord:
    """An individual verified piece of evidence."""

    id: str
    source_type: str
    content: str
    timestamp: Optional[str] = None
    service: Optional[str] = None
    commit_id: Optional[str] = None
    deployment_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not isinstance(self.id, str) or not self.id.strip():
            errors.append("Evidence ID must be a non-empty string.")
        if self.source_type not in ALLOWED_SOURCE_TYPES:
            errors.append(
                f"Invalid source_type '{self.source_type}'. Allowed: {sorted(ALLOWED_SOURCE_TYPES)}"
            )
        if not isinstance(self.content, str) or not self.content.strip():
            errors.append("Evidence content must be a non-empty string.")
        if self.timestamp is not None and not isinstance(self.timestamp, str):
            errors.append("Evidence timestamp must be a string or None.")
        if self.service is not None and not isinstance(self.service, str):
            errors.append("Evidence service must be a string or None.")
        if self.commit_id is not None and not isinstance(self.commit_id, str):
            errors.append("Evidence commit_id must be a string or None.")
        if self.deployment_id is not None and not isinstance(self.deployment_id, str):
            errors.append("Evidence deployment_id must be a string or None.")
        if not isinstance(self.metadata, dict):
            errors.append("Evidence metadata must be a dictionary.")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvidenceRecord:
        if not isinstance(data, dict):
            raise ValidationError("EvidenceRecord data must be a dict.")
        record = cls(
            id=str(data.get("id", "")),
            source_type=str(data.get("source_type", "manual")),
            content=str(data.get("content", "")),
            timestamp=data.get("timestamp"),
            service=data.get("service"),
            commit_id=data.get("commit_id"),
            deployment_id=data.get("deployment_id"),
            metadata=dict(data.get("metadata", {})),
        )
        errors = record.validate()
        if errors:
            raise ValidationError("; ".join(errors))
        return record


@dataclass
class Finding:
    """A single finding supported by evidence citations."""

    claim: str
    severity: str
    confidence: str
    evidence_ids: List[str]
    explanation: str
    recommended_next_action: str

    def validate(self, known_evidence_ids: Optional[Set[str]] = None) -> List[str]:
        errors: List[str] = []
        if not isinstance(self.claim, str) or not self.claim.strip():
            errors.append("Finding claim must be a non-empty string.")
        if self.severity not in ALLOWED_SEVERITIES:
            errors.append(
                f"Finding severity '{self.severity}' invalid. Allowed: {sorted(ALLOWED_SEVERITIES)}"
            )
        if self.confidence not in ALLOWED_CONFIDENCES:
            errors.append(
                f"Finding confidence '{self.confidence}' invalid. Allowed: {sorted(ALLOWED_CONFIDENCES)}"
            )
        if not isinstance(self.evidence_ids, list) or not self.evidence_ids:
            errors.append("Finding must reference at least one evidence ID.")
        elif not all(isinstance(eid, str) and eid.strip() for eid in self.evidence_ids):
            errors.append("Finding evidence_ids must be non-empty strings.")
        else:
            if known_evidence_ids is not None:
                unknown = set(self.evidence_ids) - known_evidence_ids
                if unknown:
                    errors.append(
                        f"Finding references nonexistent evidence IDs: {sorted(unknown)}"
                    )
            # High confidence policy: requires at least 2 distinct corroborating evidence citations
            if self.confidence == "high" and len(set(self.evidence_ids)) < 2:
                errors.append(
                    "High confidence finding requires at least 2 distinct supporting evidence IDs."
                )
        if not isinstance(self.explanation, str) or not self.explanation.strip():
            errors.append("Finding explanation must be a non-empty string.")
        if (
            not isinstance(self.recommended_next_action, str)
            or not self.recommended_next_action.strip()
        ):
            errors.append("Finding recommended_next_action must be a non-empty string.")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], known_evidence_ids: Optional[Set[str]] = None
    ) -> Finding:
        if not isinstance(data, dict):
            raise ValidationError("Finding data must be a dict.")
        finding = cls(
            claim=str(data.get("claim", "")),
            severity=str(data.get("severity", "medium")),
            confidence=str(data.get("confidence", "low")),
            evidence_ids=list(data.get("evidence_ids", [])),
            explanation=str(data.get("explanation", "")),
            recommended_next_action=str(
                data.get("recommended_next_action", "Investigate further.")
            ),
        )
        errors = finding.validate(known_evidence_ids=known_evidence_ids)
        if errors:
            raise ValidationError("; ".join(errors))
        return finding


@dataclass
class Hypothesis:
    """A plausible root-cause explanation for an incident."""

    title: str
    rank: int
    likelihood: str
    supporting_evidence_ids: List[str]
    contradicting_evidence_ids: List[str] = field(default_factory=list)
    missing_telemetry: List[str] = field(default_factory=list)
    explanation: str = ""

    def validate(self, known_evidence_ids: Optional[Set[str]] = None) -> List[str]:
        errors: List[str] = []
        if not isinstance(self.title, str) or not self.title.strip():
            errors.append("Hypothesis title must be a non-empty string.")
        if not isinstance(self.rank, int) or self.rank < 1:
            errors.append("Hypothesis rank must be a positive integer.")
        if self.likelihood not in ALLOWED_HYPOTHESIS_LIKELIHOODS:
            errors.append(
                f"Hypothesis likelihood '{self.likelihood}' invalid. Allowed: {sorted(ALLOWED_HYPOTHESIS_LIKELIHOODS)}"
            )
        if not isinstance(self.supporting_evidence_ids, list):
            errors.append("supporting_evidence_ids must be a list.")
        elif known_evidence_ids is not None:
            unknown = set(self.supporting_evidence_ids) - known_evidence_ids
            if unknown:
                errors.append(
                    f"Hypothesis references nonexistent supporting evidence: {sorted(unknown)}"
                )
        if not isinstance(self.contradicting_evidence_ids, list):
            errors.append("contradicting_evidence_ids must be a list.")
        elif known_evidence_ids is not None:
            unknown = set(self.contradicting_evidence_ids) - known_evidence_ids
            if unknown:
                errors.append(
                    f"Hypothesis references nonexistent contradicting evidence: {sorted(unknown)}"
                )
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], known_evidence_ids: Optional[Set[str]] = None
    ) -> Hypothesis:
        if not isinstance(data, dict):
            raise ValidationError("Hypothesis data must be a dict.")
        hypo = cls(
            title=str(data.get("title", "")),
            rank=int(data.get("rank", 1)),
            likelihood=str(data.get("likelihood", "possible")),
            supporting_evidence_ids=list(data.get("supporting_evidence_ids", [])),
            contradicting_evidence_ids=list(data.get("contradicting_evidence_ids", [])),
            missing_telemetry=list(data.get("missing_telemetry", [])),
            explanation=str(data.get("explanation", "")),
        )
        errors = hypo.validate(known_evidence_ids=known_evidence_ids)
        if errors:
            raise ValidationError("; ".join(errors))
        return hypo


@dataclass
class InvestigationReport:
    """The complete investigation report produced by code review or incident analysis."""

    summary: str
    findings: List[Finding]
    unknowns: List[str]
    recommendations: List[str]
    alternative_hypotheses: List[Hypothesis] = field(default_factory=list)
    execution_metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self, known_evidence_ids: Optional[Set[str]] = None) -> List[str]:
        errors: List[str] = []
        if not isinstance(self.summary, str) or not self.summary.strip():
            errors.append("InvestigationReport summary must be a non-empty string.")
        if not isinstance(self.findings, list):
            errors.append("InvestigationReport findings must be a list.")
        else:
            for i, f in enumerate(self.findings):
                if not isinstance(f, Finding):
                    errors.append(f"findings[{i}] is not a Finding instance.")
                else:
                    errors.extend(f.validate(known_evidence_ids=known_evidence_ids))

        if not isinstance(self.unknowns, list) or not all(
            isinstance(u, str) for u in self.unknowns
        ):
            errors.append("InvestigationReport unknowns must be a list of strings.")

        if not isinstance(self.recommendations, list) or not all(
            isinstance(r, str) for r in self.recommendations
        ):
            errors.append(
                "InvestigationReport recommendations must be a list of strings."
            )

        if not isinstance(self.alternative_hypotheses, list):
            errors.append(
                "InvestigationReport alternative_hypotheses must be a list."
            )
        else:
            for i, h in enumerate(self.alternative_hypotheses):
                if not isinstance(h, Hypothesis):
                    errors.append(
                        f"alternative_hypotheses[{i}] is not a Hypothesis instance."
                    )
                else:
                    errors.extend(h.validate(known_evidence_ids=known_evidence_ids))

        if not isinstance(self.execution_metadata, dict):
            errors.append("InvestigationReport execution_metadata must be a dictionary.")

        return errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "findings": [f.to_dict() for f in self.findings],
            "unknowns": list(self.unknowns),
            "recommendations": list(self.recommendations),
            "alternative_hypotheses": [h.to_dict() for h in self.alternative_hypotheses],
            "execution_metadata": dict(self.execution_metadata),
        }

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], known_evidence_ids: Optional[Set[str]] = None
    ) -> InvestigationReport:
        if not isinstance(data, dict):
            raise ValidationError("InvestigationReport data must be a dict.")

        findings_data = data.get("findings", [])
        if not isinstance(findings_data, list):
            raise ValidationError("findings must be a list.")
        findings = [
            Finding.from_dict(item, known_evidence_ids=known_evidence_ids)
            for item in findings_data
        ]

        hypo_data = data.get("alternative_hypotheses", [])
        if not isinstance(hypo_data, list):
            raise ValidationError("alternative_hypotheses must be a list.")
        hypotheses = [
            Hypothesis.from_dict(item, known_evidence_ids=known_evidence_ids)
            for item in hypo_data
        ]

        report = cls(
            summary=str(data.get("summary", "")),
            findings=findings,
            unknowns=list(data.get("unknowns", [])),
            recommendations=list(data.get("recommendations", [])),
            alternative_hypotheses=hypotheses,
            execution_metadata=dict(data.get("execution_metadata", {})),
        )
        errors = report.validate(known_evidence_ids=known_evidence_ids)
        if errors:
            raise ValidationError("; ".join(errors))
        return report


@dataclass
class CorrelationLink:
    """An association connecting code review artifacts and incident events."""

    relation_type: str  # "exact_commit_match", "deployment_match", "service_match", "temporal_proximity"
    basis: str
    review_claim: str
    incident_event_id: str
    service: Optional[str] = None
    commit_id: Optional[str] = None
    deployment_id: Optional[str] = None
    is_causal_proof: bool = False  # NEVER True: correlation does not prove causation!
    caution_note: str = (
        "ASSOCIATION ONLY: A matching identifier or timestamp proximity is circumstantial "
        "and does not constitute proof of causation."
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CorrelationReport:
    """Report linking code review findings to production incident events."""

    summary: str
    correlations: List[CorrelationLink]
    unlinked_review_findings: List[str]
    unlinked_incident_events: List[str]
    causation_disclaimer: str = (
        "DISCLAIMER: Correlated events reflect temporal, service, or identifier overlap. "
        "They are hypotheses requiring diagnostic verification, not verified causal proof."
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "correlations": [c.to_dict() for c in self.correlations],
            "unlinked_review_findings": list(self.unlinked_review_findings),
            "unlinked_incident_events": list(self.unlinked_incident_events),
            "causation_disclaimer": self.causation_disclaimer,
        }


@dataclass
class EvaluationCase:
    """A deterministic test case fixture for evaluation."""

    id: str
    category: str
    description: str
    input_data: Dict[str, Any]
    expected: Dict[str, Any] = field(default_factory=dict)
    prohibited_claims: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvaluationCase:
        return cls(
            id=str(data.get("id", "")),
            category=str(data.get("category", "general")),
            description=str(data.get("description", "")),
            input_data=dict(data.get("input_data", {})),
            expected=dict(data.get("expected", {})),
            prohibited_claims=list(data.get("prohibited_claims", [])),
        )
