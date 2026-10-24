"""Output guardrail: block contact details that are not in the curated data.

The instruction already tells the model never to invent phone numbers, URLs,
emails or social handles. This callback enforces it in code: every reply is
scanned before the user sees it, and any contact detail that isn't in
data/authorities.json (or in the user's own message) is replaced with a
placeholder and a note.
"""

import re
import unicodedata
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse

from .tools import _authorities

REMOVED = "[removed: unverified contact]"
NOTE = (
    "\n\n_Note: a contact detail that is not in Namma Civic Agent's verified "
    "data was removed from this reply. Check the authority's official website "
    "for contact details._"
)

URL_RE = re.compile(r"(?:https?://|www\.)[^\s)\]>]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
HANDLE_RE = re.compile(r"(?<![\w@])@[A-Za-z0-9_]{3,}")
# Phone numbers: 6+ digits, optionally with +, spaces or dashes in between.
LONG_NUMBER_RE = re.compile(r"\+?\d[\d -]{4,}\d")
# Short helpline codes (3-5 digits) only count when the line talks about calling.
SHORT_NUMBER_RE = re.compile(r"(?<![\d-])\d{3,5}(?![\d-])")
DATE_RE = re.compile(r"\d{1,2}[- ]\d{1,2}[- ]\d{2,4}")
CALL_CONTEXT_RE = re.compile(
    r"\b(call|dial|helpline|phone|toll[- ]?free|hotline|contact|whatsapp|sms|number)\b",
    re.IGNORECASE,
)


def _digits(text: str) -> str:
    # Normalises non-ASCII digits too, e.g. Kannada numerals.
    return "".join(str(unicodedata.digit(c)) for c in text if c.isdigit())


def _allowed_values() -> set:
    data = _authorities()
    values = {data["emergency"]["value"]}
    for authority in data["authorities"]:
        values.update(c["value"] for c in authority["channels"] if c["value"])
    return values


def _user_text(callback_context: CallbackContext) -> str:
    content = getattr(callback_context, "user_content", None)
    parts = getattr(content, "parts", None) or []
    return " ".join(p.text for p in parts if getattr(p, "text", None))


def redact_unverified_contacts(text: str, allowed: set, user_text: str = "") -> tuple:
    """Returns (cleaned_text, number_of_redactions)."""
    allowed_text = {v.lower() for v in allowed if _digits(v) != v}
    allowed_digits = {_digits(v) for v in allowed if _digits(v)}
    user_lower = user_text.lower()
    user_digits = _digits(user_text)
    count = 0

    def keep_text(value: str) -> bool:
        v = value.lower().rstrip(".,;:")
        return any(v == a or v.startswith(a) for a in allowed_text) or v in user_lower

    def keep_number(value: str) -> bool:
        if DATE_RE.fullmatch(value.strip()):
            return True
        d = _digits(value)
        return d in allowed_digits or (len(d) >= 3 and d in user_digits)

    def sub(pattern, keep, s):
        def repl(m):
            nonlocal count
            if keep(m.group(0)):
                return m.group(0)
            count += 1
            return REMOVED

        return pattern.sub(repl, s)

    lines = []
    for line in text.split("\n"):
        line = sub(URL_RE, keep_text, line)
        line = sub(EMAIL_RE, keep_text, line)
        line = sub(HANDLE_RE, keep_text, line)
        line = sub(LONG_NUMBER_RE, keep_number, line)
        if CALL_CONTEXT_RE.search(line):
            line = sub(SHORT_NUMBER_RE, keep_number, line)
        lines.append(line)
    return "\n".join(lines), count


def block_unverified_contacts(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> Optional[LlmResponse]:
    """ADK after_model_callback that redacts unverified contact details."""
    if not llm_response.content or not llm_response.content.parts:
        return None

    allowed = _allowed_values()
    user_text = _user_text(callback_context)
    total = 0
    for part in llm_response.content.parts:
        if part.text and not getattr(part, "thought", False):
            part.text, count = redact_unverified_contacts(part.text, allowed, user_text)
            total += count

    if total == 0:
        return None
    last_text = next(p for p in reversed(llm_response.content.parts) if p.text)
    last_text.text += NOTE
    return llm_response
