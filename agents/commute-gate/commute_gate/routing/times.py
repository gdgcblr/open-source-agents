from __future__ import annotations

import re


def parse_hhmm(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(\d{1,2}):(\d{2})", value.strip())
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def format_hhmm(minutes: int) -> str:
    minutes = minutes % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def pick_departure(departures: list[str], leave_by: str | None, arrive_by: str | None, duration_min: int) -> str | None:
    parsed = [parse_hhmm(item) for item in departures]
    valid = [item for item in parsed if item is not None]
    if not valid:
        return None
    if leave_by:
        leave = parse_hhmm(leave_by)
        if leave is not None:
            later = [item for item in valid if item >= leave]
            return format_hhmm(later[0] if later else valid[-1])
    if arrive_by:
        arrive = parse_hhmm(arrive_by)
        if arrive is not None:
            latest_dep = arrive - duration_min
            earlier = [item for item in valid if item <= latest_dep]
            return format_hhmm(earlier[-1] if earlier else valid[0])
    return format_hhmm(valid[0])
