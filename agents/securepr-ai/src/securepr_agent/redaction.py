"""Deterministic credential redaction for SecurePR Agent."""
import re
from typing import Tuple

SECRET_PATTERNS = [
    # AWS Access Key
    (re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"), "[REDACTED_AWS_KEY]"),
    # Generic Private Key
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    # Generic API Key / Secret assignments
    (re.compile(r"(?i)(api[_-]?key|secret|password|token|bearer|auth[_-]?key)\s*[:=]\s*['\"]([^'\"]{8,})['\"]"), r"\1='[REDACTED_CREDENTIAL]'"),
    # JWT Patterns (header.payload.signature)
    (re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}"), "[REDACTED_JWT_TOKEN]"),
    # DB URI Credentials
    (re.compile(r"(postgres|mysql|mongodb|redis):\/\/([^:]+):([^@]+)@"), r"\1://\2:[REDACTED_PASS]@"),
    # GitHub Personal Access Token
    (re.compile(r"(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36}"), "[REDACTED_GITHUB_TOKEN]"),
    # Slack Webhook / Token
    (re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}"), "[REDACTED_SLACK_TOKEN]"),
    # Stripe Secret Key
    (re.compile(r"sk_live_[0-9a-zA-Z]{24,}"), "[REDACTED_STRIPE_KEY]"),
]


class Redactor:
    """Safe, non-destructive string redactor."""

    def __init__(self):
        self.redaction_counter = 0

    def redact_text(self, text: str) -> Tuple[str, int]:
        redacted = text
        local_count = 0
        for pattern, replacement in SECRET_PATTERNS:
            matches = list(pattern.finditer(redacted))
            if matches:
                local_count += len(matches)
                redacted = pattern.sub(replacement, redacted)

        self.redaction_counter += local_count
        return redacted, local_count

    def scrub_snippet(self, raw_snippet: str) -> str:
        clean_text, _ = self.redact_text(raw_snippet)
        return clean_text
