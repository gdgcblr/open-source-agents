"""Template rendering with the anti-hallucination guard.

The LLM writes *templates* with {slots}. It must never type amounts, dates or
numbers itself; the guard rejects any template that does. Slots are filled
from the ledger, so a wrong amount in a reminder is structurally impossible.
"""

import re

SLOTS = {
    "client_name", "client_first_name", "invoice_no", "amount_due", "invoice_amount",
    "issue_date", "due_date", "days_overdue", "sender_name", "payment_details",
}

_SLOT = re.compile(r"\{([a-z_]+)\}")
_DIGIT = re.compile(r"\d")
_CURRENCY = re.compile(r"(₹|\$|€|£|\b(rs|inr|usd|eur|gbp)\b\.?)", re.IGNORECASE)
_NUMBER_WORDS = re.compile(
    r"\b(rupees?|lakhs?|lacs?|crores?|thousand|hundred|hazaar|hazar|dollars?)\b", re.IGNORECASE)

# Phrases that are never acceptable below a given tone level.
_ALWAYS_BANNED = ["police", "court", "lawyer", "sue", "legal action", "blacklist", "defaulter",
                  "fraud", "cheat"]
_BANNED_BELOW_FINAL = ["final notice", "last warning", "consequences", "escalate", "legal"]


def _phrase(p: str) -> re.Pattern:
    return re.compile(rf"\b{re.escape(p)}\b", re.IGNORECASE)


_ALWAYS_BANNED_RE = [(p, _phrase(p)) for p in _ALWAYS_BANNED]
_BANNED_BELOW_FINAL_RE = [(p, _phrase(p)) for p in _BANNED_BELOW_FINAL]


def template_problems(template: str, tone_level: int, field: str) -> list[str]:
    problems = []
    if template.count("{") != template.count("}"):
        problems.append(f"{field}: unbalanced braces")
    for slot in _SLOT.findall(template):
        if slot not in SLOTS:
            problems.append(f"{field}: unknown slot {{{slot}}}")
    text = _SLOT.sub("", template)
    if _DIGIT.search(text):
        problems.append(f"{field}: contains digits outside slots (use {{amount_due}}, {{due_date}} etc.)")
    if _CURRENCY.search(text):
        problems.append(f"{field}: contains a currency symbol or code outside slots")
    if m := _NUMBER_WORDS.search(text):
        problems.append(f"{field}: contains number word '{m[0]}' (use slots for amounts)")
    banned = _ALWAYS_BANNED_RE + (_BANNED_BELOW_FINAL_RE if tone_level < 3 else [])
    for phrase, pattern in banned:
        if pattern.search(text):
            problems.append(f"{field}: phrase '{phrase}' not allowed at tone level {tone_level}")
    return problems


def fill(template: str, values: dict[str, str]) -> str:
    return _SLOT.sub(lambda m: values[m[1]], template)
