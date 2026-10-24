"""Checks used before storage, model calls, and invitation creation."""

import json
import re

SECRET_PATTERNS = (
    r"-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|ENCRYPTED|PGP MESSAGE)[A-Z0-9 ]*-----",
    r"\b(?:password|passwd|pwd|secret|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret)\b[\"']?\s*(?::|=|\bis\b)\s*[\"']?\S+",
    r"\b(?:AIza[\w-]{25,}|sk-[\w-]{16,}|gh[pousr]_[\w]{20,}|AKIA[A-Z0-9]{16})\b",
    r"\bBearer\s+\S+",
    r"[a-z][a-z0-9+.-]*://[^\s/:]+:[^\s/@]+@",
    r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
    r"\b(?:ENC\[|AGE-ENCRYPTION\.ORG|age-encryption\.org|gAAAAA)[^\s]*",
    # Reject long opaque payloads too; this deliberately favors false positives.
    r"(?<![A-Za-z0-9])[A-Za-z0-9+/=_-]{80,}(?![A-Za-z0-9])",
)
PRIVATE_REQUEST = re.compile(
    r"\b(?:show|reveal|read|tell|list|fetch|display|share|what)\b.{0,120}"
    r"\b(?:someone else'?s|other people'?s|their|his|her|\w+'s)\b.{0,80}"
    r"\b(?:agenda|meeting details|meeting title|notes|description|password)\b",
    re.I | re.S,
)


def check_text(text: str, limit: int = 4000) -> str:
    if not isinstance(text, str) or len(text) > limit:
        raise ValueError(f"Use text of at most {limit} characters.")
    if any(re.search(pattern, text, re.I) for pattern in SECRET_PATTERNS):
        raise ValueError("Possible secret or encrypted credential detected. Remove it before continuing.")
    return text.strip()


def check_private_request(text: str) -> None:
    if PRIVATE_REQUEST.search(text):
        raise ValueError("Other people's meeting details are private. I can only help with availability and this draft.")


def validate_meeting(data: dict) -> dict:
    """Use an explicit allowlist; model/user input cannot set approval or owner."""
    from datetime import date, datetime
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    title = check_text(data.get("title", ""), 120)
    purpose = check_text(data.get("purpose", ""), 2000)
    agenda = check_text(data.get("agenda", ""), 4000)
    check_private_request(purpose)
    if not title:
        raise ValueError("Enter a meeting title.")
    emails = data.get("attendees", "")
    if not isinstance(emails, str):
        raise ValueError("Enter attendee emails separated by commas.")
    check_text(emails, 2000)
    attendees = list(dict.fromkeys(email.strip().lower() for email in emails.split(",") if email.strip()))
    if not 1 <= len(attendees) <= 10 or any(
        not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}", email)
        or len(email) > 254 for email in attendees
    ):
        raise ValueError("Enter 1–10 valid attendee email addresses.")
    try:
        duration = int(data.get("duration", 30))
        first = date.fromisoformat(data["date_from"])
        last = date.fromisoformat(data["date_to"])
        timezone = str(data["timezone"])
        ZoneInfo(timezone)
        hour_start = int(data.get("hour_start", 9))
        hour_end = int(data.get("hour_end", 17))
    except (ValueError, KeyError, TypeError, ZoneInfoNotFoundError):
        raise ValueError("Choose valid dates, an IANA timezone, and working hours.") from None
    if not 15 <= duration <= 180:
        raise ValueError("Duration must be between 15 and 180 minutes.")
    if not 0 <= hour_start < hour_end <= 23 or (hour_end - hour_start) * 60 < duration:
        raise ValueError("Working hours must fit the meeting duration.")
    if first < datetime.now(ZoneInfo(timezone)).date() or last < first or (last - first).days > 14:
        raise ValueError("Choose a future date range of at most 15 days.")
    return dict(title=title, purpose=purpose, agenda=agenda, attendees=attendees,
                duration=duration, date_from=first.isoformat(), date_to=last.isoformat(),
                timezone=timezone, hour_start=hour_start, hour_end=hour_end,
                include_weekends=data.get("include_weekends") in (True, "on", "yes"))


def model_context(meeting: dict, message: str) -> str:
    """Emails, identities, calendar responses, and tokens never enter this payload."""
    check_private_request(message)
    payload = {"request": check_text(message), "title": check_text(meeting["title"], 120),
               "purpose": check_text(meeting["purpose"], 2000), "agenda": check_text(meeting["agenda"]),
               "duration_minutes": meeting["duration"]}
    for key, value in payload.items():
        if isinstance(value, str):
            payload[key] = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email omitted]", value)
    return json.dumps(payload)
