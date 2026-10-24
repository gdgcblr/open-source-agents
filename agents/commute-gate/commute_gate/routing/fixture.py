from __future__ import annotations

import json
from pathlib import Path

from commute_gate.models import CommuteSlots, RouteLeg, RoutePlan
from commute_gate.places import resolve_place

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "routes.json"


def _normalize(name: str) -> str:
    place = resolve_place(name)
    if place:
        return place["id"]
    return " ".join(name.strip().lower().split())


class FixtureRouteProvider:
    name = "fixture"

    def get_routes(self, slots: CommuteSlots) -> RoutePlan:
        table = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        origin = _normalize(slots.origin or "")
        dest = _normalize(slots.destination or "")
        time_part = (
            f"arrive:{slots.arrive_by.strip()}"
            if slots.arrive_by
            else f"leave:{(slots.leave_by or '').strip()}"
        )
        key = f"{origin}|{dest}|{time_part}"
        if key not in table:
            raise ValueError(f"No fixture route for '{key}'.")
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
            raw={"provider": self.name, "key": key, **payload},
        )
