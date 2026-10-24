"""Deterministic slot calculation over anonymous busy intervals."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def aware_datetime(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamps must include a UTC offset.")
    return result.astimezone(timezone.utc)


def find_slots(date_from: str, date_to: str, timezone_name: str,
               duration_minutes: int, hour_start: int, hour_end: int,
               busy: list[dict], now: str = "", include_weekends: bool = False) -> dict:
    """Return up to six exact meeting slots on a 15-minute grid."""
    first, last = date.fromisoformat(date_from), date.fromisoformat(date_to)
    zone = ZoneInfo(timezone_name)
    if last < first or (last - first).days > 14:
        raise ValueError("Search range must be 1–15 days.")
    if not 15 <= duration_minutes <= 180 or not 0 <= hour_start < hour_end <= 23:
        raise ValueError("Invalid duration or working hours.")
    if len(busy) > 5000:
        raise ValueError("Too many busy intervals.")
    intervals = [(aware_datetime(item["start"]), aware_datetime(item["end"])) for item in busy]
    if any(end <= start for start, end in intervals):
        raise ValueError("Invalid busy interval.")
    current_time = aware_datetime(now) if now else datetime.now(timezone.utc)
    length = timedelta(minutes=duration_minutes)
    slots = []
    for offset in range((last - first).days + 1):
        day = first + timedelta(days=offset)
        if day.weekday() >= 5 and not include_weekends:
            continue
        cursor = datetime.combine(day, time(hour_start), zone).astimezone(timezone.utc)
        end_of_day = datetime.combine(day, time(hour_end), zone).astimezone(timezone.utc)
        while cursor + length <= end_of_day:
            end = cursor + length
            # Round-tripping avoids offering non-existent wall times at DST boundaries.
            local = cursor.astimezone(zone)
            if cursor > current_time and hour_start <= local.hour < hour_end and not any(
                cursor < busy_end and end > busy_start for busy_start, busy_end in intervals
            ):
                slots.append({"start": local.isoformat(), "end": end.astimezone(zone).isoformat()})
                if len(slots) == 6:
                    return {"slots": slots}
            cursor += timedelta(minutes=15)
    return {"slots": slots}
