from __future__ import annotations

import re

from commute_gate.models import CommuteSlots
from commute_gate.places import all_place_names, resolve_place

CONSTRAINT_PATTERNS = (
    (r"\bno[-\s]?metro\b", "no_metro"),
    (r"\bavoid metro\b", "no_metro"),
    (r"\bonly metro\b", "metro_only"),
    (r"\b(?:by|via|take|using)\s+metro\b", "metro_only"),
    (r"\bno[-\s]?bus\b", "no_bus"),
    (r"\bwheelchair\b", "accessibility"),
)


def parse_slots_from_text(text: str) -> CommuteSlots:
    """Rule-based slot fill used as fallback when no LLM is available."""
    lowered = text.lower()
    origin = _extract_origin(text)
    destination = _extract_destination(text)
    arrive_by = _extract_time(lowered, ("arrive", "reach", "by"))
    leave_by = _extract_time(lowered, ("leave", "start", "after"))
    constraints = [
        flag for pattern, flag in CONSTRAINT_PATTERNS if re.search(pattern, lowered)
    ]
    if origin and destination and origin.lower() == destination.lower():
        destination = None
    return CommuteSlots(
        origin=origin,
        destination=destination,
        arrive_by=arrive_by,
        leave_by=leave_by,
        constraints=constraints,
    )


def slots_from_llm_json(payload: dict) -> CommuteSlots:
    origin = _clean(payload.get("origin"))
    destination = _clean(payload.get("destination"))
    resolved_origin = resolve_place(origin)
    resolved_dest = resolve_place(destination)
    constraints = payload.get("constraints") or []
    if not isinstance(constraints, list):
        constraints = []
    return CommuteSlots(
        origin=resolved_origin["name"] if resolved_origin else origin,
        destination=resolved_dest["name"] if resolved_dest else destination,
        arrive_by=_normalize_time(_clean(payload.get("arrive_by"))),
        leave_by=_normalize_time(_clean(payload.get("leave_by"))),
        constraints=[str(item) for item in constraints],
    )


def infer_goal(text: str, slots: CommuteSlots) -> str:
    if slots.destination and slots.arrive_by:
        return f"Arrive at {slots.destination} by {slots.arrive_by} using verified Bengaluru transit data."
    if slots.destination:
        return f"Reach {slots.destination} using verified Bengaluru transit data."
    return text.strip() or "Plan a commute using verified Bengaluru transit data."


def _extract_origin(text: str) -> str | None:
    match = re.search(r"\bfrom\s+(.+?)(?:\s+to\s+|\s+towards?\s+|$)", text, flags=re.I)
    if match:
        place = resolve_place(match.group(1))
        if place:
            return place["name"]
    if re.search(r"\b(?:to|towards|reach)\b", text, flags=re.I):
        return None
    return _first_place(text)


def _extract_destination(text: str) -> str | None:
    match = re.search(
        r"\b(?:to|towards|reach|for)\s+(.+?)(?:\s+by\s+|\s+at\s+|\s+before\s+|$)",
        text,
        flags=re.I,
    )
    if match:
        place = resolve_place(match.group(1))
        if place:
            return place["name"]
    places = _all_resolved(text)
    if len(places) >= 2:
        return places[-1]["name"]
    if len(places) == 1 and not re.search(r"\bfrom\b", text, flags=re.I):
        return places[0]["name"]
    return None


def _first_place(text: str) -> str | None:
    places = _all_resolved(text)
    return places[0]["name"] if places else None


def _all_resolved(text: str) -> list[dict]:
    found: list[dict] = []
    lowered = text.lower()
    for name in sorted(all_place_names(), key=len, reverse=True):
        if re.search(rf"\b{re.escape(name.lower())}\b", lowered):
            place = resolve_place(name)
            if place and place not in found:
                found.append(place)
    return found


def _extract_time(text: str, cues: tuple[str, ...]) -> str | None:
    cue = "|".join(cues)
    match = re.search(
        rf"\b(?:{cue})\b[^0-9]{{0,12}}(\d{{1,2}})(?::(\d{{2}}))?\s*(am|pm)?",
        text,
        flags=re.I,
    )
    if match:
        return _normalize_time(
            f"{match.group(1)}:{match.group(2) or '00'} {match.group(3) or ''}"
        )
    match = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if match:
        return _normalize_time(f"{match.group(1)}:{match.group(2)}")
    return None


def _normalize_time(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", value.lower())
    if not match:
        return None
    hours = int(match.group(1))
    minutes = int(match.group(2) or 0)
    meridiem = match.group(3)
    if meridiem == "pm" and hours < 12:
        hours += 12
    if meridiem == "am" and hours == 12:
        hours = 0
    if hours > 23 or minutes > 59:
        return None
    return f"{hours:02d}:{minutes:02d}"


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {"", "null", "none", "unknown", "n/a"}:
        return None
    return text
