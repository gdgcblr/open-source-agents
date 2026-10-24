"""Detector catalogue. Each detector finds one kind of secret or PII.

`secret=True`  -> replaced with [REDACTED:KIND]            (no need to correlate)
`secret=False` -> replaced with a pseudonym [KIND:abc123]  (same value -> same pseudonym in a run,
                  so the model can still tell 'same user' from 'different user')
`group`        -> which regex group is replaced (so labels like TOKEN= or http:// are kept)
"""
import ipaddress
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Optional

_BENIGN_USERS = {"runner", "runneradmin", "vsts", "ubuntu", "root", "circleci", "jenkins", "build",
                 "buildkite-agent", "gitlab-runner", "user", "shared", "public", "default"}


@dataclass(frozen=True)
class Detector:
    kind: str
    pattern: re.Pattern
    secret: bool = False
    group: int = 0
    validate: Optional[Callable[[str], bool]] = None


def _not_marker(v: str) -> bool:
    return not v.startswith("[")


def _luhn(v: str) -> bool:
    digits = [int(c) for c in v if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return total % 10 == 0


def _ipv4(v: str) -> bool:
    try:
        ip = ipaddress.IPv4Address(v)
    except ValueError:
        return False
    return not (ip.is_loopback or ip.is_unspecified)


def _ipv6(v: str) -> bool:
    try:
        ip = ipaddress.IPv6Address(v)
    except ValueError:
        return False
    return not (ip.is_loopback or ip.is_unspecified)


def _home_user(v: str) -> bool:
    return _not_marker(v) and v.lower() not in _BENIGN_USERS


I = re.IGNORECASE
DETECTORS: list[Detector] = [
    # ---- secrets
    Detector("PRIVATE_KEY", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), secret=True),
    Detector("GITHUB_TOKEN", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"), secret=True),
    Detector("AWS_ACCESS_KEY", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), secret=True),
    Detector("GOOGLE_API_KEY", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"), secret=True),
    Detector("SLACK_TOKEN", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"), secret=True),
    Detector("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"), secret=True),
    Detector("BEARER", re.compile(r"\b(bearer|basic)\s+([A-Za-z0-9\-._~+/=]{8,})", I), secret=True, group=2, validate=_not_marker),
    Detector("URL_CREDENTIALS", re.compile(r"\b[a-z][a-z0-9+.\-]*://([^/\s:@]+:[^/\s@]+)@", I), secret=True, group=1, validate=_not_marker),
    Detector(
        "SECRET_ASSIGNMENT",
        re.compile(r"\b([A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY)[A-Z0-9_]*)\s*[=:]\s*['\"]?([^\s'\"]+)", I),
        secret=True, group=2, validate=_not_marker,
    ),
    # ---- PII (pseudonymised)
    Detector("EMAIL", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    Detector("CREDIT_CARD", re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])"), validate=_luhn),
    Detector("SSN", re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")),
    Detector("AADHAAR", re.compile(r"(?<![\d.])(?<!\d\s)[2-9]\d{3}\s\d{4}\s\d{4}(?![\d.])(?!\s\d)")),
    Detector("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    Detector("MAC_ADDRESS", re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")),
    Detector("IPV6", re.compile(r"(?<![\w:.])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])"), validate=_ipv6),
    Detector("IPV4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), validate=_ipv4),
    Detector("PHONE", re.compile(r"(?<![\w.])\+\d{1,3}[\s-]?\(?\d{2,5}\)?[\s-]?\d{3,5}[\s-]?\d{3,5}(?![\w])")),
    Detector("PHONE", re.compile(r"(?<![\w.])[6-9]\d{9}(?![\w.])")),
    Detector("PHONE", re.compile(r"(?<![\w.])\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?![\w.])")),
    Detector("HOME_USER", re.compile(r"(?:/home/|/Users/|[A-Za-z]:\\Users\\)([^/\\\s]+)"), group=1, validate=_home_user),
    Detector("INTERNAL_HOST", re.compile(r"\b(?:[a-z0-9-]+\.)+(?:internal|corp|local|lan|intranet|intra)\b(?:\.[a-z0-9-]+)*", I)),
]


@lru_cache(maxsize=8)
def _compile_terms(raw: str) -> Optional[Detector]:
    terms = [t.strip() for t in raw.split(",") if len(t.strip()) >= 3]
    if not terms:
        return None
    return Detector("CUSTOM_TERM", re.compile(r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")\b", I))


def custom_detector() -> Optional[Detector]:
    """Names, customers or project codenames cannot be found by pattern. Users list them in
    TRIAGE_REDACT_TERMS (comma separated) and they are treated like any other PII."""
    return _compile_terms(os.environ.get("TRIAGE_REDACT_TERMS", ""))
