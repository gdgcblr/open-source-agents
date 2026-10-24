"""Read a scheduling request locally; attendee addresses never go to Gemini."""

from datetime import date, datetime, timedelta
import re
from zoneinfo import ZoneInfo

from guardrails import check_private_request, check_text, validate_meeting


def meeting_request(message):
    message = check_text(message, 2000)
    check_private_request(message)
    # shortcut: accept a clear request format; add model parsing only if broader language is needed.
    match = re.fullmatch(r"(?:schedule\s+)?(.+?)\s+on\s+(today|tomorrow|\d{4}-\d{2}-\d{2})\s+with\s+(.+)", message, re.I | re.S)
    parts = [part.strip() for part in message.split("|")]
    if match:
        title, day, attendees = match.groups()
    elif len(parts) == 3:
        title, day, attendees = parts
    else:
        raise ValueError("Use: Project kickoff on YYYY-MM-DD with person@example.com. Or: Meeting name | YYYY-MM-DD | attendee emails.")
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    try:
        selected = {"today": today, "tomorrow": today + timedelta(days=1)}.get(day.lower())
        selected = selected or date.fromisoformat(day)
    except ValueError:
        raise ValueError("Use a valid YYYY-MM-DD date, today, or tomorrow.") from None
    title = check_text(title, 120)
    return validate_meeting({
        "title": title, "attendees": attendees, "date_from": selected.isoformat(),
        "date_to": selected.isoformat(), "duration": 30, "timezone": "Asia/Kolkata",
        "hour_start": 9, "hour_end": 17, "include_weekends": True,
        "purpose": f"Discuss {title} and agree on outcomes and next steps.",
        "agenda": f"Context and goals for {title} — 5 minutes\nDiscuss {title} — 20 minutes\nDecisions, owners, and next steps — 5 minutes",
    })
