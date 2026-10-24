"""Deterministic safety checks and guardrails for AgentRelay reports and evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from agentrelay.schemas import (
    ALLOWED_CONFIDENCES,
    ALLOWED_SEVERITIES,
    InvestigationReport,
)

ALLOWED_CONFIDENCE = ALLOWED_CONFIDENCES
ALLOWED_SEVERITY = ALLOWED_SEVERITIES

REQUIRED_REPORT_FIELDS = {
    "summary",
    "findings",
    "unknowns",
    "recommendations",
}
ALLOWED_REPORT_FIELDS = REQUIRED_REPORT_FIELDS | {
    "alternative_hypotheses",
    "execution_metadata",
}

REQUIRED_FINDING_FIELDS = {"claim", "evidence_ids", "confidence"}
ALLOWED_FINDING_FIELDS = REQUIRED_FINDING_FIELDS | {
    "severity",
    "explanation",
    "recommended_next_action",
}

# These patterns flag suspicious content for review. They are not a complete
# prompt-injection detector, and matching text is never executed as an instruction.
SUSPICIOUS_PATTERNS = [
    re.compile(r"ignore (all )?(previous|prior) instructions", re.I),
    re.compile(r"reveal (the )?(system prompt|secrets|api keys)", re.I),
    re.compile(r"you are now (an? )?(admin|system)", re.I),
    re.compile(r"disregard above", re.I),
    re.compile(r"output only ['\"]?confirmed['\"]?", re.I),
]


class ReportRejected(ValueError):
    """Raised when a report fails deterministic safety checks."""


def load_json(path: str | Path) -> Any:
    """Safely load and parse a JSON file."""
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)


def inspect_untrusted_text(text: str) -> list[str]:
    """Return warnings for suspicious instructions embedded in untrusted evidence."""
    if not isinstance(text, str):
        return []
    return [
        f"Suspicious instruction pattern: {pattern.pattern}"
        for pattern in SUSPICIOUS_PATTERNS
        if pattern.search(text)
    ]


def validate_report(
    report: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> list[str]:
    """Validate report structure, evidence references, and conservative confidence.

    An empty list means deterministic checks passed.
    """
    errors: list[str] = []

    if not isinstance(report, dict):
        return ["Report must be a JSON object."]

    missing = REQUIRED_REPORT_FIELDS - report.keys()
    extra = report.keys() - ALLOWED_REPORT_FIELDS
    if missing:
        errors.append(f"Missing report fields: {sorted(missing)}")
    if extra:
        errors.append(f"Unexpected report fields: {sorted(extra)}")

    if missing or extra:
        return errors

    if not isinstance(report["summary"], str) or not report["summary"].strip():
        errors.append("summary must be a non-empty string.")

    if not isinstance(report["findings"], list):
        errors.append("findings must be a list.")
        findings = []
    else:
        findings = report["findings"]

    if not isinstance(report["unknowns"], list) or not all(
        isinstance(item, str) for item in report["unknowns"]
    ):
        errors.append("unknowns must be a list of strings.")

    if not isinstance(report["recommendations"], list) or not all(
        isinstance(item, str) for item in report["recommendations"]
    ):
        errors.append("recommendations must be a list of strings.")

    # Validate optional alternative_hypotheses if present
    if "alternative_hypotheses" in report:
        if not isinstance(report["alternative_hypotheses"], list):
            errors.append("alternative_hypotheses must be a list.")

    # Validate optional execution_metadata if present
    if "execution_metadata" in report:
        if not isinstance(report["execution_metadata"], dict):
            errors.append("execution_metadata must be a dictionary.")

    known_ids = {
        item.get("id")
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }

    for index, finding in enumerate(findings):
        prefix = f"findings[{index}]"

        if not isinstance(finding, dict):
            errors.append(f"{prefix} must be an object.")
            continue

        missing_finding = REQUIRED_FINDING_FIELDS - finding.keys()
        extra_finding = finding.keys() - ALLOWED_FINDING_FIELDS
        if missing_finding:
            errors.append(
                f"{prefix} missing required keys: {sorted(missing_finding)}"
            )
            continue
        if extra_finding:
            errors.append(
                f"{prefix} contains unexpected keys: {sorted(extra_finding)}"
            )
            continue

        claim = finding["claim"]
        refs = finding["evidence_ids"]
        confidence = finding["confidence"]

        if not isinstance(claim, str) or not claim.strip():
            errors.append(f"{prefix}.claim must be a non-empty string.")

        if not isinstance(refs, list) or not refs:
            errors.append(f"{prefix} needs at least one evidence ID.")
        elif not all(isinstance(ref, str) for ref in refs):
            errors.append(f"{prefix}.evidence_ids must contain strings.")
        else:
            unknown_refs = set(refs) - known_ids
            if unknown_refs:
                errors.append(
                    f"{prefix} references unknown evidence: "
                    f"{sorted(unknown_refs)}"
                )

        if confidence not in ALLOWED_CONFIDENCE:
            errors.append(
                f"{prefix}.confidence must be one of "
                f"{sorted(ALLOWED_CONFIDENCE)}."
            )

        if confidence == "high" and isinstance(refs, list) and len(set(refs)) < 2:
            errors.append(
                f"{prefix}: high confidence requires at least two "
                "distinct evidence IDs."
            )

        # Validate severity if present
        if "severity" in finding:
            severity = finding["severity"]
            if severity not in ALLOWED_SEVERITY:
                errors.append(
                    f"{prefix}.severity must be one of {sorted(ALLOWED_SEVERITY)}."
                )

    # Evidence untrusted input validation
    for item in evidence:
        if not isinstance(item, dict):
            errors.append("Every evidence item must be an object.")
            continue

        if not isinstance(item.get("id"), str) or not item["id"]:
            errors.append("Every evidence item needs a non-empty string ID.")

        content = item.get("content", "")
        if not isinstance(content, str):
            errors.append(
                f"Evidence {item.get('id', '<unknown>')} content must be text."
            )
            continue

        for warning in inspect_untrusted_text(content):
            errors.append(
                f"Evidence {item.get('id', '<unknown>')}: {warning}"
            )

    return errors


def require_valid_report(
    report: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> None:
    """Enforce that report satisfies safety checks, raising ReportRejected if invalid."""
    errors = validate_report(report, evidence)
    if errors:
        raise ReportRejected("\n".join(errors))
