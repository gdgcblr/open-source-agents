from __future__ import annotations

import json
from pathlib import Path

from commute_gate.models import CommuteSlots, RouteLeg, RoutePlan

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "routes.json"


def _normalize_place(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _route_key(slots: CommuteSlots) -> str:
    origin = _normalize_place(slots.origin or "")
    dest = _normalize_place(slots.destination or "")
    if slots.arrive_by:
        time_part = f"arrive:{slots.arrive_by.strip()}"
    else:
        time_part = f"leave:{slots.leave_by.strip()}"
    return f"{origin}|{dest}|{time_part}"


def load_fixture_table() -> dict[str, dict]:
    with FIXTURE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def get_routes(slots: CommuteSlots) -> RoutePlan:
    """Return schedule-backed route data (fixture-backed for offline OSS use)."""
    table = load_fixture_table()
    key = _route_key(slots)
    if key not in table:
        available = ", ".join(sorted(table.keys())[:5])
        raise ValueError(
            f"No fixture route for key '{key}'. "
            f"Add an entry to fixtures/routes.json or use a demo preset. "
            f"Sample keys: {available}"
        )

    payload = table[key]
    legs = [
        RouteLeg(
            mode=item["mode"],
            line=item["line"],
            duration_min=int(item["duration_min"]),
            departure=item["departure"],
        )
        for item in payload["legs"]
    ]
    return RoutePlan(
        origin=slots.origin or "",
        destination=slots.destination or "",
        legs=legs,
        total_duration_min=int(payload["total_duration_min"]),
        arrival=payload["arrival"],
        raw=payload,
    )
