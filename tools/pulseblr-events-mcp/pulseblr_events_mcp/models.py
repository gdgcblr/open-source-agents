"""Small, explicitly public event contract shared by both sources."""

import math
import re
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .errors import SourceError

EVENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
_SENSITIVE_QUERY_KEYS = {
    "key",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "secret",
    "password",
    "signature",
    "sig",
    "code",
}


def _text(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = "".join(c for c in value if c.isprintable() or c in "\n\t").strip()
    return cleaned[:limit] or None


def _url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or any(ord(c) < 33 for c in value)
        ):
            return None
        query = urlencode(
            [
                (k, v)
                for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                if k.casefold() not in _SENSITIVE_QUERY_KEYS
            ]
        )
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))
    except ValueError:
        return None


def _instant(value: object) -> str:
    if not isinstance(value, str) or len(value) > 64:
        raise SourceError("The public source returned an invalid event timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed.isoformat()
    except (ValueError, OverflowError):
        raise SourceError("The public source returned an invalid event timestamp.") from None


def normalize_event(raw: object) -> dict:
    """Discard unknown fields, bound text, validate instants and sanitize public links."""
    if not isinstance(raw, dict):
        raise SourceError("The public source returned an invalid event record.")
    event_id = raw.get("id")
    title = _text(raw.get("title"), 300)
    url = _url(raw.get("url"))
    event_format = raw.get("format")
    if (
        not isinstance(event_id, str)
        or not EVENT_ID.fullmatch(event_id)
        or not title
        or not url
        or not isinstance(event_format, str)
        or event_format not in {"online", "offline", "hybrid"}
    ):
        raise SourceError("The public source returned an invalid event record.")
    result = {
        "id": event_id,
        "title": title,
        "url": url,
        "startsAt": _instant(raw.get("startsAt")),
        "format": event_format,
        "isOnline": event_format == "online",
        "categories": [],
        "connectionScore": 0,
    }
    if raw.get("endsAt") is not None:
        try:
            result["endsAt"] = _instant(raw["endsAt"])
        except SourceError:
            result["endTimeStatus"] = "invalid"
    elif raw.get("endTimeStatus") == "invalid":
        result["endTimeStatus"] = "invalid"
    for field in (
        "venue",
        "area",
        "city",
        "location",
        "organizer",
        "price",
        "source",
        "startsAtIST",
        "connectionRating",
        "address",
        "hasFood",
    ):
        value = _text(raw.get(field), 300)
        if value:
            result[field] = value
    description = _text(raw.get("description"), 1200)
    if description:
        result["description"] = description
        result["description_is_untrusted"] = True
    for field in ("categories", "tags", "companies", "seenInSources"):
        values = raw.get(field)
        if isinstance(values, list):
            result[field] = list(
                dict.fromkeys(text for value in values[:32] if (text := _text(value, 100)))
            )
    for field in ("registerUrl", "sourceUrl"):
        value = _url(raw.get(field))
        if value:
            result[field] = value
    for field in ("isFree", "soldOut"):
        if isinstance(raw.get(field), bool):
            result[field] = raw[field]
    for field in ("attendeeCount", "capacity"):
        value = raw.get(field)
        if type(value) is int and 0 <= value <= 10_000_000:
            result[field] = value
    score = raw.get("connectionScore")
    if type(score) is int:
        result["connectionScore"] = max(0, min(100, score))
    elif type(score) is float and math.isfinite(score):
        result["connectionScore"] = max(0, min(100, float(score)))
    return result
