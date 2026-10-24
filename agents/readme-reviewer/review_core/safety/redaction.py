"""Credential detection, redaction and the ADK model callbacks built on it.

  * redact_model_input  (before_model_callback): strips credentials from everything about to be
    sent to the model - the user's message, file contents and tool results.
  * block_secret_output (after_model_callback): replaces any model answer that contains one.

The same patterns drive scan_for_secrets, so the scanner and the guardrail never disagree.
"""

import logging
import re

from google.adk.models.llm_response import LlmResponse
from google.genai import types

logger = logging.getLogger(__name__)

REDACTED = "[REDACTED]"
BLOCKED_MESSAGE = "[blocked: the model's answer contained something that looks like a credential]"

SECRET_PATTERNS = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "OpenAI-style key": re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    "NVIDIA API key": re.compile(r"nvapi-[A-Za-z0-9_\-]{20,}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    "Slack token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "Private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "Hardcoded secret assignment": re.compile(
        r"""(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*["'][A-Za-z0-9_\-\.]{16,}["']"""
    ),
}

# A quoted value like "your_api_key_here_please" is documentation, not a leaked secret.
PLACEHOLDER = re.compile(r"(?i)your|example|placeholder|changeme|xxxx|dummy|sample|<|\*\*\*")


def _is_real(label: str, match: "re.Match") -> bool:
    return not (label == "Hardcoded secret assignment" and PLACEHOLDER.search(match.group(0)))


def find_credentials(text: str) -> list:
    """Labels of the credential patterns found in text (placeholders ignored)."""
    return [
        label
        for label, pattern in SECRET_PATTERNS.items()
        if any(_is_real(label, m) for m in pattern.finditer(text))
    ]


def contains_credential(text: str) -> bool:
    return bool(find_credentials(text))


def redact(text: str) -> str:
    """Replace every credential in text with [REDACTED]."""
    for label, pattern in SECRET_PATTERNS.items():
        text = pattern.sub(lambda m, label=label: REDACTED if _is_real(label, m) else m.group(0), text)
    return text


def redact_value(value):
    """Redact every string inside nested dicts, lists and tuples."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(redact_value(v) for v in value)
    return value


def response_text(llm_response) -> str:
    parts = getattr(getattr(llm_response, "content", None), "parts", None) or []
    return "".join(p.text for p in parts if getattr(p, "text", None))


def redact_model_input(callback_context, llm_request):
    """ADK `before_model_callback`: redact credentials in the request before the model sees it."""
    redacted = 0
    for content in llm_request.contents or []:
        for part in content.parts or []:
            if part.text:
                clean = redact(part.text)
                redacted += clean != part.text
                part.text = clean
            if part.function_response and part.function_response.response is not None:
                clean = redact_value(part.function_response.response)
                redacted += clean != part.function_response.response
                part.function_response.response = clean
    if redacted:
        logger.warning("Redacted credentials from %d part(s) before calling the model", redacted)
    return None


def block_secret_output(callback_context, llm_response):
    """ADK `after_model_callback`: replace a model answer that contains a credential."""
    if contains_credential(response_text(llm_response)):
        logger.warning("Blocked a model answer that contained a credential")
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=BLOCKED_MESSAGE)]))
    return None
