from __future__ import annotations

import json
from pathlib import Path

from commute_gate.models import CommuteSlots, RouteLeg, RoutePlan
from commute_gate.places import resolve_place
from commute_gate.routing.metro import metro_legs
from commute_gate.routing.times import format_hhmm, parse_hhmm, pick_departure

CORRIDORS = Path(__file__).resolve().parent.parent / "fixtures" / "bmtc_corridors.json"


class BengaluruRouteProvider:
    name = "bengaluru"

    def __init__(self) -> None:
        self.corridors = {}
        if CORRIDORS.exists():
            payload = json.loads(CORRIDORS.read_text(encoding="utf-8"))
            self.corridors = payload.get("pairs") or {}

    def get_routes(self, slots: CommuteSlots) -> RoutePlan:
        origin = resolve_place(slots.origin)
        dest = resolve_place(slots.destination)
        if not origin or not dest:
            raise ValueError("Origin or destination is not a known Bengaluru place.")
        if origin["id"] == dest["id"]:
            raise ValueError("Origin and destination resolve to the same place.")

        bus_plan = self._bus_plan(origin, dest, slots)
        metro_plan = self._metro_plan(origin, dest, slots)

        if "metro_only" in slots.constraints:
            chosen, other = metro_plan, bus_plan
        elif "no_metro" in slots.constraints:
            chosen, other = bus_plan, None
        elif "no_bus" in slots.constraints:
            chosen, other = metro_plan, None
        else:
            chosen, other = _prefer(bus_plan, metro_plan)

        if not chosen:
            raise ValueError(
                f"No BMTC/metro corridor found between {origin['name']} and {dest['name']}."
            )
        if other:
            chosen.raw.setdefault("alternatives", [])
            chosen.raw["alternatives"].append(_summarize_plan(other))
            chosen.raw["choice_reason"] = chosen.raw.get("choice_reason") or (
                f"Selected {chosen.legs[0].mode} as the faster grounded option; "
                f"also computed a {other.legs[0].mode} alternative."
            )
        return chosen

    def _bus_plan(self, origin: dict, dest: dict, slots: CommuteSlots) -> RoutePlan | None:
        record = self._best_corridor(origin["id"], dest["id"])
        if not record:
            return None
        stops = [str(item) for item in record.get("stops") or []]
        i = _best_stop_index(stops, origin)
        j = _best_stop_index(stops, dest)
        if i is None or j is None:
            return None
        hops = abs(j - i) or 1
        duration = max(12, hops * 2)
        depart = pick_departure(
            record.get("departures") or [],
            slots.leave_by,
            slots.arrive_by,
            duration,
        ) or "08:00"
        arrival = format_hhmm((parse_hhmm(depart) or 0) + duration)
        return RoutePlan(
            origin=origin["name"],
            destination=dest["name"],
            legs=[
                RouteLeg(
                    mode="bus",
                    line=str(record.get("route") or "BMTC"),
                    duration_min=duration,
                    departure=depart,
                )
            ],
            total_duration_min=duration,
            arrival=arrival,
            raw={
                "provider": self.name,
                "source": "Vonter/bmtc-gtfs",
                "route_name": record.get("full_name"),
                "board": stops[i],
                "alight": stops[j],
                "hops": hops,
            },
        )

    def _metro_plan(self, origin: dict, dest: dict, slots: CommuteSlots) -> RoutePlan | None:
        depart = slots.leave_by or "08:00"
        if slots.arrive_by and not slots.leave_by:
            arrive = parse_hhmm(slots.arrive_by) or 9 * 60
            depart = format_hhmm(max(0, arrive - 40))
        legs = metro_legs(origin, dest, depart)
        if not legs:
            return None
        total = sum(leg.duration_min for leg in legs)
        start = parse_hhmm(legs[0].departure) or 0
        return RoutePlan(
            origin=origin["name"],
            destination=dest["name"],
            legs=legs,
            total_duration_min=total,
            arrival=format_hhmm(start + total),
            raw={"provider": self.name, "source": "Namma Metro station graph"},
        )

    def _best_corridor(self, origin_id: str, dest_id: str) -> dict | None:
        forward = self.corridors.get(f"{origin_id}|{dest_id}") or []
        reverse = self.corridors.get(f"{dest_id}|{origin_id}") or []
        candidates = list(forward) + list(reverse)
        scored: list[tuple[int, dict]] = []
        origin = {"id": origin_id, "name": origin_id, "stop_hints": [origin_id]}
        dest = {"id": dest_id, "name": dest_id, "stop_hints": [dest_id]}
        from commute_gate.places import resolve_place

        origin_place = resolve_place(origin_id) or origin
        dest_place = resolve_place(dest_id) or dest
        for record in candidates:
            stops = [str(item) for item in record.get("stops") or []]
            i = _best_stop_index(stops, origin_place)
            j = _best_stop_index(stops, dest_place)
            if i is None or j is None:
                continue
            scored.append((abs(j - i), record))
        if not scored:
            return None
        return min(scored, key=lambda item: item[0])[1]


def _prefer(bus: RoutePlan | None, metro: RoutePlan | None) -> tuple[RoutePlan | None, RoutePlan | None]:
    if bus and metro:
        # Prefer metro when times are close: less sensitive to peak traffic.
        if metro.total_duration_min <= bus.total_duration_min + 12:
            metro.raw["choice_reason"] = (
                f"Metro {metro.total_duration_min} min vs bus {bus.total_duration_min} min; "
                "preferring metro when close."
            )
            return metro, bus
        bus.raw["choice_reason"] = (
            f"Bus {bus.total_duration_min} min is clearly faster than metro "
            f"{metro.total_duration_min} min."
        )
        return bus, metro
    return (bus or metro), None


def _summarize_plan(plan: RoutePlan) -> dict:
    return {
        "mode": plan.legs[0].mode if plan.legs else None,
        "lines": [leg.line for leg in plan.legs],
        "total_duration_min": plan.total_duration_min,
        "departure": plan.legs[0].departure if plan.legs else None,
        "arrival": plan.arrival,
        "legs": [
            {
                "mode": leg.mode,
                "line": leg.line,
                "duration_min": leg.duration_min,
                "departure": leg.departure,
            }
            for leg in plan.legs
        ],
    }


def _best_stop_index(stops: list[str], place: dict) -> int | None:
    hints = [place["id"], place["name"].lower(), *(place.get("stop_hints") or [])]
    for idx, stop in enumerate(stops):
        blob = stop.lower()
        if any(hint.lower() in blob for hint in hints):
            return idx
    return None
