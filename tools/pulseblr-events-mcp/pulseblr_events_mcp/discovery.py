"""Deterministic time windows, public-event filtering and organiser evidence."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .errors import InputError

IST = ZoneInfo("Asia/Kolkata")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_WORDS = re.compile(r"[^\w]+", re.UNICODE)


def _clock(now: datetime | None) -> datetime:
    value = datetime.now(IST) if now is None else now
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InputError("now must be a timezone-aware datetime")
    return value.astimezone(IST)


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except (ValueError, OverflowError):
            return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    try:
        return value.astimezone(IST)
    except (ValueError, OverflowError):
        return None


def _date_bound(value: str, *, end: bool) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise InputError("Date boundaries must be ISO dates or timezone-aware ISO timestamps")
    value = value.strip()
    try:
        if _DATE.fullmatch(value):
            day = date.fromisoformat(value)
            if end:
                day += timedelta(days=1)
            return datetime.combine(day, time.min, IST)
    except (ValueError, OverflowError) as exc:
        raise InputError("Invalid calendar date boundary") from exc
    result = _timestamp(value)
    if result is None:
        raise InputError("Date boundaries require valid ISO dates or timezone-aware timestamps")
    return result


def resolve_window(
    when: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return an IST half-open window; date-only end boundaries include that day."""
    clock = _clock(now)
    if when is not None and (date_from is not None or date_to is not None):
        raise InputError("Use a named window or explicit dates, not both")
    try:
        if date_from is not None or date_to is not None:
            start = _date_bound(date_from, end=False) if date_from is not None else clock
            end = (
                _date_bound(date_to, end=True) if date_to is not None else start + timedelta(days=7)
            )
        else:
            if when is None:
                when = "rolling7d"
            if not isinstance(when, str):
                raise InputError("when must be a supported named window")
            key = when.strip().casefold()
            midnight = datetime.combine(clock.date(), time.min, IST)
            if key == "today":
                start, end = midnight, midnight + timedelta(days=1)
            elif key == "tomorrow":
                start, end = midnight + timedelta(days=1), midnight + timedelta(days=2)
            elif key == "weekend":
                days_to_saturday = -1 if clock.weekday() == 6 else (5 - clock.weekday()) % 7
                start = midnight + timedelta(days=days_to_saturday)
                end = start + timedelta(days=2)
            elif key in {"rolling7d", "week", "next_7_days", "next7days", "next_7d"}:
                start, end = clock, clock + timedelta(days=7)
            else:
                raise InputError("when must be today, tomorrow, weekend or rolling7d")
        if end <= start:
            raise InputError("date_to must be after date_from")
        return start, end
    except OverflowError as exc:
        raise InputError("Date window is outside supported calendar bounds") from exc


def _text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _words(value: Any) -> str:
    return " ".join(_WORDS.sub(" ", _text(value).casefold()).split())


def _contains(haystack: str, needle: str) -> bool:
    return bool(needle) and f" {needle} " in f" {haystack} "


def _format(value: Any) -> str:
    key = _words(value)
    if key in {"in person", "inperson", "physical", "offline"}:
        return "in-person"
    if key in {"virtual", "online"}:
        return "online"
    return key


def _interests(interests: list[str] | None) -> list[str]:
    if interests is None:
        return []
    if not isinstance(interests, list) or len(interests) > 20:
        raise InputError("interests must be a list of at most 20 strings")
    cleaned: dict[str, str] = {}
    for value in interests:
        if not isinstance(value, str) or not _words(value) or len(value) > 100:
            raise InputError("Each interest must be a non-empty string of at most 100 characters")
        cleaned.setdefault(_words(value), _text(value))
    return list(cleaned.values())


def _connection_score(event: dict) -> float:
    value = event.get("connectionScore", 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    if isinstance(value, float) and not math.isfinite(value):
        return 0.0
    return float(max(0, min(100, value)))


def _rank(event: dict, interests: list[str]) -> tuple[float, list[str]]:
    categories = (
        [_words(value) for value in event.get("categories", []) if isinstance(value, str)]
        if isinstance(event.get("categories"), list)
        else []
    )
    keywords = _words(" ".join(_text(event.get(key)) for key in ("title", "description")))
    score = _connection_score(event)
    matched = []
    for interest in interests:
        key = _words(interest)
        if any(_contains(category, key) for category in categories):
            score += 20
            matched.append(interest)
        elif _contains(keywords, key):
            score += 5
            matched.append(interest)
    return round(score, 6), matched


def _events(events: list[dict], *, maximum: int | None = None) -> tuple[list[dict], list[str]]:
    if not isinstance(events, list):
        raise InputError("events must be a list of public event objects")
    if maximum is not None and len(events) > maximum:
        raise InputError(f"At most {maximum} candidate events are supported")
    result = []
    seen = set()
    duplicate_count = 0
    invalid_count = 0
    for event in events:
        if not isinstance(event, dict):
            raise InputError("Each event must be a public event object")
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id.strip():
            invalid_count += 1
            continue
        if event_id in seen:
            duplicate_count += 1
            continue
        seen.add(event_id)
        result.append(event)
    warnings = []
    if duplicate_count:
        warnings.append(f"Removed {duplicate_count} duplicate event ID(s).")
    if invalid_count:
        warnings.append(f"Excluded {invalid_count} event(s) without a usable public ID.")
    return result, warnings


def _filter_choices(value: str | list[str] | None, name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not 1 <= len(value) <= 40:
        raise InputError(f"{name} must be a name or a list of at most 40 names")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 100 for item in value):
        raise InputError(f"{name} must contain non-empty strings of at most 100 characters")
    return value


def filter_events(events: list[dict], filters: dict, now: datetime | None) -> list[dict]:
    """Apply explicit discovery filters, then exclude started/invalid-start rows."""
    clock = _clock(now)
    if not isinstance(filters, dict):
        raise InputError("filters must be an object")
    for key in ("query", "format", "sort"):
        if filters.get(key) is not None and not isinstance(filters[key], str):
            raise InputError(f"{key} must be a string")
    if filters.get("free") is not None and not isinstance(filters["free"], bool):
        raise InputError("free must be a boolean")
    limit = filters.get("limit", 50)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise InputError("limit must be an integer from 1 to 50")
    has_window = any(filters.get(key) is not None for key in ("when", "dateFrom", "dateTo"))
    bounds = (
        resolve_window(filters.get("when"), filters.get("dateFrom"), filters.get("dateTo"), clock)
        if has_window
        else None
    )
    query_patterns = [
        re.compile(r"\b" + re.escape(term))
        for term in _text(filters.get("query")).casefold().split()
    ]
    categories_wanted = {
        _words(value) for value in _filter_choices(filters.get("category"), "category")
    }
    areas_wanted = {
        _text(value).casefold() for value in _filter_choices(filters.get("area"), "area")
    }
    wanted_format = _format(filters.get("format"))
    result = []
    unique, _ = _events(events)
    for event in unique:
        start = _timestamp(event.get("startsAt"))
        if start is None or start < clock or (bounds and not bounds[0] <= start < bounds[1]):
            continue
        categories = event.get("categories", [])
        categories = categories if isinstance(categories, list) else []
        searchable = " ".join(
            str(event.get(key, ""))
            for key in ("title", "organizer", "venue", "description", "categories")
        ).casefold()
        if any(pattern.search(searchable) is None for pattern in query_patterns):
            continue
        if categories_wanted and not any(
            _words(value) in categories_wanted for value in categories
        ):
            continue
        if areas_wanted and _text(event.get("area")).casefold() not in areas_wanted:
            continue
        if wanted_format and _format(event.get("format")) != wanted_format:
            continue
        if filters.get("free") is True and event.get("isFree") is not True:
            continue
        if filters.get("free") is False and event.get("isFree") is not False:
            continue
        result.append(event)
    sort = _text(filters.get("sort")).casefold()
    if sort in {"connections", "connection", "connection_score", "networking"}:
        result.sort(
            key=lambda event: (
                -_connection_score(event),
                _timestamp(event["startsAt"]),
                event["id"],
            )
        )
    elif sort not in {"relevance", "popular", "newest"}:
        result.sort(key=lambda event: (_timestamp(event["startsAt"]), event["id"]))
    return result[:limit]


def recommend_communities(
    events: list[dict], interests: list[str] | None = None, limit: int = 5
) -> dict:
    """Infer organisers only from the supplied public-event corpus."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
        raise InputError("limit must be an integer from 1 to 10")
    wanted = _interests(interests)
    unique, warnings = _events(events, maximum=50)
    groups: dict[str, dict] = {}
    missing = 0
    for event in unique:
        name = _text(event.get("organizer"))
        if not name:
            missing += 1
            continue
        score, matched = _rank(event, wanted)
        group = groups.setdefault(
            name.casefold(), {"organizer": name, "events": [], "score": 0.0, "matched": set()}
        )
        group["events"].append((score, event))
        group["score"] += score
        group["matched"].update(matched)
    if missing:
        warnings.append(f"Omitted {missing} event(s) with no observed organiser.")
    communities = []
    for group in groups.values():
        evidence = sorted(
            group["events"], key=lambda row: (-row[0], _text(row[1].get("startsAt")), row[1]["id"])
        )
        matches = [value for value in wanted if value in group["matched"]]
        communities.append(
            {
                "organizer": group["organizer"],
                "observed_event_count": len(evidence),
                "matched_interests": matches,
                "score": round(group["score"], 6),
                "representative_events": [
                    {key: row.get(key) for key in ("id", "title", "url", "startsAt")}
                    for _, row in evidence[:3]
                ],
                "reason": f"Observed organising {len(evidence)} event(s) in this candidate set."
                + (f" Matches: {', '.join(matches)}." if matches else ""),
            }
        )
    communities.sort(
        key=lambda row: (-row["score"], -row["observed_event_count"], row["organizer"].casefold())
    )
    if not communities:
        warnings.append("No communities can be inferred from the observed organisers.")
    warnings.append(
        "Organiser evidence is not a verified membership or contact directory; scores are ranking signals, not probabilities."
    )
    return {
        "communities": communities[:limit],
        "warnings": warnings,
        "candidate_count": len(unique),
    }
