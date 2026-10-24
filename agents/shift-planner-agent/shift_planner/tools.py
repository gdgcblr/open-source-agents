"""Read-only analysis tools for the shift planner. All maths is plain Python, no LLM involved."""
import csv
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
REQUIRED = ["date", "start_time", "end_time", "area", "earnings", "km", "fuel_cost"]
BLOCKS = [("morning", 6, 11), ("afternoon", 11, 16), ("evening", 16, 21)]  # else: night


def _block(hour: int) -> str:
    for name, lo, hi in BLOCKS:
        if lo <= hour < hi:
            return name
    return "night"


def _resolve(csv_path: str) -> Path:
    p = (PROJECT_DIR / csv_path).resolve()
    if PROJECT_DIR != p and PROJECT_DIR not in p.parents:
        raise ValueError("csv_path must be inside the project folder")
    return p


def _read(csv_path: str) -> list:
    p = _resolve(csv_path)
    with open(p, newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Missing columns: {missing}. Need: {REQUIRED}")
        out = []
        for i, r in enumerate(reader, start=2):
            try:
                d = date.fromisoformat(r["date"])
                s = datetime.strptime(r["start_time"], "%H:%M")
                e = datetime.strptime(r["end_time"], "%H:%M")
                hours = ((e - s).seconds / 3600) or 24.0
                net = float(r["earnings"]) - float(r["fuel_cost"])
            except (ValueError, KeyError) as ex:
                raise ValueError(f"Bad value on line {i}: {ex}")
            out.append({"day": d.strftime("%A"), "weekend": d.weekday() >= 5, "area": r["area"].strip(),
                        "block": _block(s.hour), "hours": hours, "net": net})
        return out


def load_trips(csv_path: str = "sample_trips.csv") -> dict:
    """Validates a shifts CSV and gives a quick overview.

    Args:
        csv_path: CSV file inside the project folder. Columns: date, start_time (HH:MM),
            end_time (HH:MM), area, earnings (INR), km, fuel_cost (INR).

    Returns:
        A dict with shift count, areas and date range, or an error message.
    """
    try:
        rows = _read(csv_path)
        with open(_resolve(csv_path), newline="") as f:
            dates = sorted(r["date"] for r in csv.DictReader(f))
    except (ValueError, OSError) as e:
        return {"status": "error", "error": str(e)}
    return {"status": "ok", "shifts": len(rows), "areas": sorted({r["area"] for r in rows}),
            "first_date": dates[0], "last_date": dates[-1]}


def earnings_summary(group_by: str, csv_path: str = "sample_trips.csv") -> dict:
    """Net earnings per hour (earnings minus fuel), grouped by area, time block or weekday.

    Args:
        group_by: One of 'area', 'block' (morning/afternoon/evening/night) or 'day' (weekday name).
        csv_path: CSV file inside the project folder.

    Returns:
        A dict with groups sorted by net_per_hour (INR), highest first.
    """
    key = {"area": "area", "block": "block", "day": "day"}.get(group_by)
    if not key:
        return {"status": "error", "error": "group_by must be 'area', 'block' or 'day'"}
    try:
        rows = _read(csv_path)
    except (ValueError, OSError) as e:
        return {"status": "error", "error": str(e)}
    return {"status": "ok", "group_by": group_by, "groups": _aggregate(rows, lambda r: r[key])}


def best_slots(top_n: int = 3, weekend: str = "any", csv_path: str = "sample_trips.csv") -> dict:
    """Best area + time-block combinations by net earnings per hour.

    Args:
        top_n: How many slots to return (1 to 10).
        weekend: 'yes' for weekend only, 'no' for weekdays only, 'any' for all days.
        csv_path: CSV file inside the project folder.

    Returns:
        A dict with the top slots. Slots with fewer than 2 shifts are ignored as too noisy.
    """
    try:
        rows = _read(csv_path)
    except (ValueError, OSError) as e:
        return {"status": "error", "error": str(e)}
    if weekend == "yes":
        rows = [r for r in rows if r["weekend"]]
    elif weekend == "no":
        rows = [r for r in rows if not r["weekend"]]
    groups = [g for g in _aggregate(rows, lambda r: f'{r["area"]} / {r["block"]}') if g["shifts"] >= 2]
    return {"status": "ok", "weekend_filter": weekend, "slots": groups[:max(1, min(top_n, 10))]}


def _aggregate(rows, keyfn) -> list:
    acc = defaultdict(lambda: [0.0, 0.0, 0])
    for r in rows:
        a = acc[keyfn(r)]
        a[0] += r["net"]; a[1] += r["hours"]; a[2] += 1
    out = [{"name": k, "net_per_hour": round(v[0] / v[1], 1), "shifts": v[2], "hours": round(v[1], 1)}
           for k, v in acc.items() if v[1] > 0]
    return sorted(out, key=lambda g: g["net_per_hour"], reverse=True)
