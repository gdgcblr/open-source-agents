from __future__ import annotations

import re
from dataclasses import dataclass, field

# Patterns for untrusted user/listing content — not exhaustive.
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.I),
    re.compile(r"disregard\s+(your\s+)?(system|safety)\s+", re.I),
    re.compile(r"you\s+are\s+now\s+(a\s+)?(?:DAN|unrestricted)", re.I),
    re.compile(r"reveal\s+(your\s+)?(system\s+)?prompt", re.I),
    re.compile(r"output\s+(api\s+)?key", re.I),
]

PII_PATTERNS = [
    (re.compile(r"\b\d{10}\b"), "[phone redacted]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[email redacted]"),
    (re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"), "[id redacted]"),
    (re.compile(r"\b(?:Aadhaar|aadhar)\s*(?:no\.?|number)?\s*[:#]?\s*\d", re.I), "[id redacted]"),
]

ABUSE_PATTERNS = [
    re.compile(r"\b(kill|murder)\s+you\b", re.I),
    re.compile(r"\b(i\s+will\s+)?rape\b", re.I),
]

SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key|secret|password|otp)\s*[:=]\s*\S+", re.I),
    re.compile(r"\b\d{6}\b.*\b(?:otp|one[- ]time)\b", re.I),
]

ACCUSATION_AS_FACT = re.compile(
    r"\b(he|she|they|landlord|owner)\s+(is\s+a\s+)?(?:criminal|thief|fraudster)\b",
    re.I,
)


@dataclass
class ModerationResult:
    allowed: bool
    status: str  # published | held | rejected
    sanitized_text: str
    flags: list[str] = field(default_factory=list)
    user_message: str = ""


def detect_injection(text: str) -> list[str]:
    hits = []
    for pat in INJECTION_PATTERNS:
        if pat.search(text):
            hits.append(f"prompt_injection:{pat.pattern[:40]}")
    return hits


def redact_pii(text: str) -> tuple[str, bool]:
    changed = False
    out = text
    for pat, repl in PII_PATTERNS:
        new, n = pat.subn(repl, out)
        if n:
            changed = True
            out = new
    return out, changed


def sanitize_untrusted_content(text: str) -> tuple[str, list[str]]:
    """Mark injection attempts; do not execute embedded instructions."""
    notes: list[str] = []
    for pat in INJECTION_PATTERNS:
        if pat.search(text):
            notes.append(
                "Untrusted content contained instruction-override language; "
                "treated as data only."
            )
    return text, notes


def strip_instruction_override(text: str) -> str:
    """Neutralize obvious override lines for agent context."""
    lines = []
    for line in text.splitlines():
        skip = False
        for pat in INJECTION_PATTERNS:
            if pat.search(line):
                skip = True
                break
        if not skip:
            lines.append(line)
    return "\n".join(lines)


def check_public_post(text: str) -> ModerationResult:
    flags: list[str] = []
    lower = text.lower()

    for pat in ABUSE_PATTERNS:
        if pat.search(text):
            flags.append("abuse_threat")
            return ModerationResult(
                allowed=False,
                status="rejected",
                sanitized_text="",
                flags=flags,
                user_message="Submission contains threatening or abusive language.",
            )

    for pat in SECRET_PATTERNS:
        if pat.search(text):
            flags.append("credential_request")

    inj = detect_injection(text)
    flags.extend(inj)

    sanitized, pii = redact_pii(text)
    if pii:
        flags.append("pii_redacted")

    if ACCUSATION_AS_FACT.search(text):
        flags.append("unverified_accusation")
        return ModerationResult(
            allowed=False,
            status="held",
            sanitized_text=sanitized,
            flags=flags,
            user_message=(
                "Submission may contain an unverified criminal accusation stated as fact. "
                "Please describe your personal experience without asserting crimes as established facts."
            ),
        )

    if "abuse_threat" in flags:
        return ModerationResult(
            allowed=False,
            status="rejected",
            sanitized_text="",
            flags=flags,
            user_message="Submission rejected.",
        )

    status = "published"
    if flags:
        if any(f.startswith("prompt_injection") for f in flags):
            status = "held"
        elif "pii_redacted" in flags:
            status = "published"  # publish redacted

    return ModerationResult(
        allowed=status != "rejected",
        status=status,
        sanitized_text=sanitized,
        flags=flags,
        user_message="",
    )


def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
