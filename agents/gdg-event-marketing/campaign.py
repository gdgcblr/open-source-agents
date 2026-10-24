from datetime import datetime, timedelta, timezone
from typing import Dict, List
import uuid


def _parse_event_time(value: str) -> datetime:
    try:
        event_time = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "Use an ISO 8601 date and time, for example "
            "2026-11-07T17:00:00+05:30."
        ) from exc
    if event_time.tzinfo is None:
        raise ValueError(
            "Include a time-zone offset, for example "
            "2026-11-07T17:00:00+05:30 or 2026-11-07T11:30:00Z."
        )
    return event_time


def build_event_campaign(event: dict) -> List[Dict[str, object]]:
    """Build a fact-grounded, editable event lifecycle sequence locally."""
    title = event.get("title", "").strip()
    description = event.get("description", "").strip()
    if not title or not description:
        raise ValueError("Add an event title and description before planning a campaign.")

    event_time = _parse_event_time(event.get("date_time", ""))
    location = event.get("location", "").strip()
    url = event.get("url", "").strip()
    details = [event_time.strftime("%a, %b %d at %I:%M %p %Z")]
    if location:
        details.append(location)
    detail_block = "\n".join(details)
    link_block = "\n\nEvent details: {}".format(url) if url else ""

    return [
        {
            "stage": "Announcement",
            "offset_days": -14,
            "scheduled_at": event_time - timedelta(days=14),
            "copy": (
                "Save the date: {}\n\n{}\n\n{}\n\n"
                "Explore the event and share it with someone who may be interested.{}"
            ).format(title, description, detail_block, link_block),
        },
        {
            "stage": "Topic spotlight",
            "offset_days": -7,
            "scheduled_at": event_time - timedelta(days=7),
            "copy": (
                "What would you like to explore?\n\n"
                "{} is coming up.\n\n{}\n\nHere are the details:\n{}{}"
            ).format(title, description, detail_block, link_block),
        },
        {
            "stage": "One-day reminder",
            "offset_days": -1,
            "scheduled_at": event_time - timedelta(days=1),
            "copy": "A reminder: {} is tomorrow.\n\n{}{}".format(
                title, detail_block, link_block
            ),
        },
        {
            "stage": "Post-event follow-up",
            "offset_days": 1,
            "scheduled_at": event_time + timedelta(days=1),
            "copy": (
                "Thanks for being part of {}!\n\n"
                "Organizer: add one real moment, attendee question, or takeaway "
                "from the event before sharing this follow-up."
            ).format(title),
        },
    ]


def _escape_ical(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _fold_ical_line(line: str) -> str:
    folded = []
    current = ""
    current_bytes = 0
    for character in line:
        char_bytes = len(character.encode("utf-8"))
        if current_bytes + char_bytes > 73:
            folded.append(current)
            current = " " + character
            current_bytes = 1 + char_bytes
        else:
            current += character
            current_bytes += char_bytes
    folded.append(current)
    return "\r\n".join(folded)


def build_campaign_ics(event: dict, campaign: List[Dict[str, object]]) -> str:
    """Export local review reminders; this never schedules or publishes posts."""
    title = event.get("title", "").strip() or "GDG community event"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//GDG Event Marketing Studio//Campaign Planner//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for item in campaign:
        scheduled_at = item["scheduled_at"]
        if not isinstance(scheduled_at, datetime):
            raise ValueError("Campaign reminder is missing a valid date and time.")
        start = scheduled_at.astimezone(timezone.utc)
        end = start + timedelta(minutes=15)
        summary = "Review {}: {}".format(item["stage"], title)
        description = (
            "Review and manually publish the {} campaign draft. "
            "This is a reminder only; nothing will be posted automatically."
        ).format(item["stage"].lower())
        lines.extend(
            [
                "BEGIN:VEVENT",
                "UID:{}@gdg-event-marketing.local".format(uuid.uuid4()),
                "DTSTAMP:{}".format(now),
                "DTSTART:{}".format(start.strftime("%Y%m%dT%H%M%SZ")),
                "DTEND:{}".format(end.strftime("%Y%m%dT%H%M%SZ")),
                "SUMMARY:{}".format(_escape_ical(summary)),
                "DESCRIPTION:{}".format(_escape_ical(description)),
                "BEGIN:VALARM",
                "TRIGGER:-PT30M",
                "ACTION:DISPLAY",
                "DESCRIPTION:{}".format(_escape_ical(summary)),
                "END:VALARM",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold_ical_line(line) for line in lines) + "\r\n"
