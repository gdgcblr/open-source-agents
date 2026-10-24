
import json
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "reports.json"


def load_reports() -> list[dict]:
    """Load commuter reports from the local JSON dataset."""
    if not DATA_FILE.exists():
        return []

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            reports = json.load(file)
    except (json.JSONDecodeError, OSError):
        return []

    return reports if isinstance(reports, list) else []


def search_reports(
    origin: str = "",
    destination: str = "",
    station: str = "",
    direction: str = "",
    interchange: str = "",
) -> dict:
    """Search commuter reports by route, station, direction, or interchange."""
    reports = load_reports()
    matches = []

    filters = {
        "origin": origin,
        "destination": destination,
        "station": station,
        "direction": direction,
        "interchange": interchange,
    }

    for report in reports:
        matched = True

        for field, requested in filters.items():
            if not requested:
                continue

            actual = str(report.get(field, ""))
            if requested.casefold() not in actual.casefold():
                matched = False
                break

        if matched:
            matches.append(report)

    return {
        "count": len(matches),
        "reports": matches[:50],
        "message": (
            "Reports found."
            if matches
            else "No matching commuter reports were found."
        ),
    }


def recommend_travel_time(
    origin: str = "",
    destination: str = "",
    direction: str = "",
) -> dict:
    """Summarize reported crowd levels by two-hour observation window."""
    result = search_reports(
        origin=origin,
        destination=destination,
        direction=direction,
    )
    reports = result["reports"]

    if not reports:
        return {
            "message": (
                "There is not enough matching report data "
                "to recommend a travel-time window."
            )
        }

    windows = {}

    for report in reports:
        observed_time = str(report.get("observed_time", ""))

        try:
            hour = int(observed_time.split(":")[0])
            if not 0 <= hour <= 23:
                continue
        except (ValueError, IndexError):
            continue

        window_start = (hour // 2) * 2
        window = f"{window_start:02d}:00-{window_start + 2:02d}:00"

        windows.setdefault(window, []).append(
            str(report.get("crowd_level", "unknown")).lower()
        )

    if not windows:
        return {
            "message": (
                "Matching reports exist, but they do not contain "
                "valid observation times."
            )
        }

    summary = []

    for window, levels in sorted(windows.items()):
        summary.append({
            "window": window,
            "report_count": len(levels),
            "crowd_levels": {
                level: levels.count(level)
                for level in sorted(set(levels))
            },
        })

    return {
        "message": (
            "These are historical report counts, not live "
            "crowd measurements or guaranteed forecasts."
        ),
        "windows": summary,
    }


def recommend_coach(
    station: str,
    interchange: str = "",
    direction: str = "",
) -> dict:
    """Summarize reported coach positions near a station or interchange."""
    result = search_reports(
        station=station,
        interchange=interchange,
        direction=direction,
    )

    reports = result["reports"]

    if not reports:
        return {
            "message": (
                "No matching reports are available to suggest "
                "a coach position."
            )
        }

    counts = {"front": 0, "middle": 0, "rear": 0}

    for report in reports:
        position = str(report.get("coach_position", "")).lower()
        if position in counts:
            counts[position] += 1

    total = sum(counts.values())

    if total == 0:
        return {
            "message": (
                "Matching reports do not include recognized coach "
                "positions. Follow official station signage."
            )
        }

    return {
        "station": station,
        "interchange": interchange,
        "reported_positions": counts,
        "message": (
            "These are positions mentioned in historical reports, "
            "not verified station-layout instructions. Follow "
            "official signage and station staff."
        ),
    }
