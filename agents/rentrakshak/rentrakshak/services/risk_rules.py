from __future__ import annotations

import re
from typing import Iterable

from rentrakshak.models.schemas import (
    ExtractedProperty,
    RedFlagFinding,
    RiskCategory,
    Severity,
)

RULES: list[tuple[str, Severity, re.Pattern[str], str, str]] = [
    (
        "RF-001",
        Severity.CRITICAL,
        re.compile(r"(?:pay|transfer|send)\s+(?:token|advance|booking)\s+(?:before|prior)", re.I),
        "Payment demanded before adequate viewing or verification.",
        "Insist on in-person viewing and written terms before any payment.",
    ),
    (
        "RF-002",
        Severity.HIGH,
        re.compile(r"(?:urgent|immediately|today only|last chance).{0,40}(?:pay|transfer|token)", re.I),
        "Urgent pressure to pay quickly.",
        "Slow down; verify identity and property independently.",
    ),
    (
        "RF-003",
        Severity.CRITICAL,
        re.compile(r"pay\s+(?:to|into)\s+(?:my\s+)?friend|third\s+party|different\s+account", re.I),
        "Request to pay an unrelated third party.",
        "Pay only to verified account matching agreement parties.",
    ),
    (
        "RF-004",
        Severity.HIGH,
        re.compile(
            r"(?:no\s+(?:in[- ]person\s+)?viewing|without\s+viewing|virtual\s+only|keys?\s+by\s+courier)",
            re.I,
        ),
        "Limited or remote-only viewing before payment.",
        "Visit the property and confirm address before paying.",
    ),
    (
        "RF-005",
        Severity.CRITICAL,
        re.compile(r"\b(?:otp|one[- ]time\s+password|password|pin)\b", re.I),
        "Request involving OTP, password, or similar secrets.",
        "Never share OTPs or passwords; report suspicious requests.",
    ),
    (
        "RF-006",
        Severity.MEDIUM,
        re.compile(r"non[- ]?refundable\s+token|token\s+not\s+refundable", re.I),
        "Unclear or strict non-refundable token terms.",
        "Get refund conditions in writing before paying.",
    ),
    (
        "RF-007",
        Severity.MEDIUM,
        re.compile(r"(?:extra|hidden|additional)\s+(?:fee|charges?)", re.I),
        "Unexplained additional fees mentioned.",
        "Ask for itemized charges and include them in the agreement.",
    ),
    (
        "RF-008",
        Severity.HIGH,
        re.compile(r"remote\s+viewing.*(?:pay|deposit)", re.I),
        "Payment linked to remote viewing or key delivery.",
        "Defer payment until physical verification.",
    ),
]


def _excerpt(text: str, match: re.Match[str], radius: int = 60) -> str:
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    snippet = text[start:end].replace("\n", " ")
    return snippet.strip()


def detect_red_flags(
    listing_text: str,
    chat_text: str | None = None,
    contradictions: Iterable[str] | None = None,
) -> list[RedFlagFinding]:
    combined = f"{listing_text or ''}\n{chat_text or ''}"
    findings: list[RedFlagFinding] = []

    for rule_id, severity, pattern, explanation, step in RULES:
        m = pattern.search(combined)
        if m:
            findings.append(
                RedFlagFinding(
                    rule_id=rule_id,
                    severity=severity,
                    evidence_excerpt=_excerpt(combined, m),
                    explanation=explanation,
                    recommended_next_step=step,
                )
            )

    for i, issue in enumerate(contradictions or [], start=1):
        findings.append(
            RedFlagFinding(
                rule_id=f"RF-C{i:02d}",
                severity=Severity.MEDIUM,
                evidence_excerpt=issue[:200],
                explanation="Contradiction between listing, chat, or structured fields.",
                recommended_next_step="Clarify discrepancies with the representative in writing.",
            )
        )

    return findings


def classify_risk(
    findings: list[RedFlagFinding],
    prop: ExtractedProperty,
) -> tuple[RiskCategory, str]:
    if any(f.severity == Severity.CRITICAL for f in findings):
        return (
            RiskCategory.CRITICAL,
            "Critical warning patterns detected in supplied text.",
        )
    if any(f.severity == Severity.HIGH for f in findings):
        return RiskCategory.HIGH, "High-concern patterns require verification before payment."
    if findings or prop.raw_notes:
        return (
            RiskCategory.NEEDS_VERIFICATION,
            "Some concerns or missing details; verify before committing.",
        )
    return (
        RiskCategory.LOW,
        "No major red-flag patterns in supplied text; independent verification still required.",
    )


def verification_actions(findings: list[RedFlagFinding], prop: ExtractedProperty) -> list[str]:
    actions = [
        "Visit the property and confirm the address matches the listing.",
        "Verify representative authority (owner/broker) with ID and property papers.",
        "Read the full rental agreement before paying deposit or advance.",
    ]
    for f in findings:
        actions.append(f.recommended_next_step)
    if not prop.locality:
        actions.append("Confirm Bengaluru locality and commute access independently.")
    return list(dict.fromkeys(actions))


def questions_to_ask(findings: list[RedFlagFinding]) -> list[str]:
    base = [
        "Who are the parties on the rental agreement?",
        "What is the exact deposit refund process and timeline?",
        "What maintenance and utility charges apply monthly?",
        "Can I speak with the current tenant or neighbor?",
    ]
    if any(f.rule_id == "RF-005" for f in findings):
        base.insert(0, "Why do you need an OTP or password for this rental process?")
    return base
