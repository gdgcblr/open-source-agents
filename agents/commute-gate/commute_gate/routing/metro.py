from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from commute_gate.models import RouteLeg
from commute_gate.routing.times import format_hhmm, parse_hhmm

METRO_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "metro_lines.json"
TRANSFER_MIN = 4
MIN_PER_HOP = 2


def load_metro() -> dict:
    return json.loads(METRO_PATH.read_text(encoding="utf-8"))


def _canonical_station(name: str, stations: list[str]) -> str | None:
    needle = name.strip().lower()
    for station in stations:
        if station.lower() == needle:
            return station
    for station in stations:
        low = station.lower()
        if needle in low or low in needle:
            return station
    return None


def stations_for_place(place: dict) -> list[tuple[str, str]]:
    """All (line, official station name) options for a neighborhood."""
    payload = load_metro()
    found: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(line: str, station: str) -> None:
        key = (line, station.lower())
        if key in seen:
            return
        seen.add(key)
        found.append((line, station))

    for hint in place.get("metro") or []:
        if ":" in hint:
            line_hint, station_hint = hint.split(":", 1)
            line = line_hint.strip().title()
            stations = payload["lines"].get(line) or []
            match = _canonical_station(station_hint, stations)
            if match:
                add(line, match)
        else:
            for line, stations in payload["lines"].items():
                match = _canonical_station(hint, stations)
                if match:
                    add(line, match)

    for line, stations in payload["lines"].items():
        match = _canonical_station(place["name"], stations) or _canonical_station(
            place["id"], stations
        )
        if match:
            add(line, match)
    return found


def metro_legs(origin_place: dict, dest_place: dict, depart: str) -> list[RouteLeg] | None:
    starts = stations_for_place(origin_place)
    ends = stations_for_place(dest_place)
    if not starts or not ends:
        return None

    payload = load_metro()
    best: list[tuple[str, str]] | None = None
    best_cost = 10**9
    end_set = {(line, station.lower()) for line, station in ends}

    for start in starts:
        path = _shortest_path(payload, start, end_set)
        if not path:
            continue
        cost = _path_minutes(path)
        if cost < best_cost:
            best_cost = cost
            best = path

    if not best:
        return None
    return _path_to_legs(best, depart)


def _shortest_path(
    payload: dict,
    start: tuple[str, str],
    ends: set[tuple[str, str]],
) -> list[tuple[str, str]] | None:
    neighbors = _neighbors(payload)
    queue: deque[tuple[str, str]] = deque([start])
    prev: dict[tuple[str, str], tuple[str, str] | None] = {start: None}

    while queue:
        current = queue.popleft()
        if (current[0], current[1].lower()) in ends:
            return _reconstruct(prev, current)
        for nxt in neighbors.get(current, []):
            if nxt not in prev:
                prev[nxt] = current
                queue.append(nxt)
    return None


def _neighbors(payload: dict) -> dict[tuple[str, str], list[tuple[str, str]]]:
    lines: dict[str, list[str]] = payload["lines"]
    graph: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for line, stations in lines.items():
        for idx, station in enumerate(stations):
            node = (line, station)
            graph.setdefault(node, [])
            if idx > 0:
                graph[node].append((line, stations[idx - 1]))
            if idx + 1 < len(stations):
                graph[node].append((line, stations[idx + 1]))

    station_to_lines: dict[str, list[str]] = {}
    for line, stations in lines.items():
        for station in stations:
            station_to_lines.setdefault(station.lower(), []).append(line)

    for station, crossing in (payload.get("interchanges") or {}).items():
        for line in crossing:
            if any(s.lower() == station.lower() for s in lines.get(line, [])):
                official = _canonical_station(station, lines[line])
                if official:
                    station_to_lines.setdefault(official.lower(), [])
                    if line not in station_to_lines[official.lower()]:
                        station_to_lines[official.lower()].append(line)

    for station_key, line_names in station_to_lines.items():
        unique_lines = list(dict.fromkeys(line_names))
        if len(unique_lines) < 2:
            continue
        for line in unique_lines:
            official = _canonical_station(station_key, lines[line])
            if not official:
                continue
            for other in unique_lines:
                if other == line:
                    continue
                other_official = _canonical_station(station_key, lines[other])
                if other_official:
                    graph.setdefault((line, official), []).append((other, other_official))
    return graph


def _reconstruct(
    prev: dict[tuple[str, str], tuple[str, str] | None],
    end: tuple[str, str],
) -> list[tuple[str, str]]:
    path = [end]
    current = end
    while prev[current] is not None:
        current = prev[current]
        path.append(current)
    path.reverse()
    return path


def _path_minutes(path: list[tuple[str, str]]) -> int:
    if len(path) < 2:
        return 8
    hops = 0
    transfers = 0
    for prev, nxt in zip(path, path[1:]):
        if prev[0] == nxt[0]:
            hops += 1
        else:
            transfers += 1
    return max(8, hops * MIN_PER_HOP + transfers * TRANSFER_MIN)


def _path_to_legs(path: list[tuple[str, str]], depart: str) -> list[RouteLeg]:
    segments: list[list[tuple[str, str]]] = []
    current = [path[0]]
    for node in path[1:]:
        if node[0] == current[-1][0]:
            current.append(node)
        else:
            segments.append(current)
            current = [node]
    segments.append(current)

    legs: list[RouteLeg] = []
    clock = parse_hhmm(depart) or 0
    for idx, segment in enumerate(segments):
        hops = max(1, len(segment) - 1)
        duration = max(6, hops * MIN_PER_HOP)
        if idx:
            clock += TRANSFER_MIN
        legs.append(
            RouteLeg(
                mode="metro",
                line=segment[0][0],
                duration_min=duration,
                departure=format_hhmm(clock),
            )
        )
        clock += duration
    return legs
