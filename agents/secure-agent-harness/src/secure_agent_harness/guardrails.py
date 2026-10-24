"""Deterministic guardrails; these complement, not replace, infrastructure controls."""
import re

from .config import Settings

_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
]
_SUSPICIOUS_MARKERS = (
    "ignore all previous instructions",
    "reveal your system prompt",
    "disable your safety",
    "send the api key",
    "exfiltrate",
)


class GuardrailViolation(ValueError):
    pass


def validate_user_input(text: str, settings: Settings) -> str:
    if not isinstance(text, str):
        raise GuardrailViolation("Request must be text.")
    text = text.strip()
    if not text:
        raise GuardrailViolation("Request cannot be empty.")
    if len(text) > settings.max_input_chars:
        raise GuardrailViolation(f"Request exceeds {settings.max_input_chars} characters.")
    return text


def redact_secrets(text: str) -> str:
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def detect_injection_markers(text: str) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in _SUSPICIOUS_MARKERS)


def validate_output(text: str, max_chars: int = 12000) -> str:
    if not isinstance(text, str):
        raise GuardrailViolation("Model returned a non-text answer.")
    text = text.strip()
    if not text:
        raise GuardrailViolation("Model returned an empty answer.")
    return text[:max_chars]


def validate_tool_name(name: str, registered_names: set[str]) -> None:
    if name not in registered_names:
        raise GuardrailViolation(f"Tool '{name}' is not registered.")
