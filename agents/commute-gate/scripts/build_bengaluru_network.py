#!/usr/bin/env python3
"""Download open BMTC route CSVs and extract corridors that touch known places.

Source: Vonter/bmtc-gtfs (community GTFS derived from Namma BMTC).
Hugging Face has no Bengaluru transit GTFS as of 2026-10; this is the open substitute.
"""
from __future__ import annotations

import ast
import csv
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "commute_gate" / "fixtures"
CACHE = ROOT / ".cache"
ROUTES_URL = "https://raw.githubusercontent.com/Vonter/bmtc-gtfs/main/csv/routes.csv"
OUTPUT = FIXTURES / "bmtc_corridors.json"

csv.field_size_limit(sys.maxsize)


def _load_places() -> list[dict]:
    payload = json.loads((FIXTURES / "places.json").read_text(encoding="utf-8"))
    return payload["places"]


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 100_000:
        print(f"Using cached {dest}")
        return dest
    print(f"Downloading {url}")
    urllib.request.urlretrieve(url, dest)
    return dest


def _place_matches(stop_blob: str, place: dict) -> bool:
    blob = stop_blob.lower()
    if place["id"] in blob or place["name"].lower() in blob:
        return True
    return any(hint.lower() in blob for hint in place.get("stop_hints", []))


def _parse_list(raw: str) -> list[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        value = ast.literal_eval(raw)
        if isinstance(value, list):
            return [str(item) for item in value]
    except (SyntaxError, ValueError):
        pass
    return [part.strip(" []'\"") for part in raw.split(",") if part.strip()]


def extract(routes_csv: Path, places: list[dict], limit_per_pair: int = 3) -> dict:
    pair_hits: dict[str, list[dict]] = {}
    with routes_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            stops = _parse_list(row.get("stop_list") or "")
            trips = _parse_list(row.get("trip_list") or "")
            stop_blob = " | ".join(stops).lower()
            matched = [place for place in places if _place_matches(stop_blob, place)]
            if len(matched) < 2:
                continue
            record = {
                "route": row.get("name") or "",
                "full_name": row.get("full_name") or "",
                "direction_id": row.get("direction_id"),
                "stop_count": int(row.get("stop_count") or len(stops) or 0),
                "stops": stops,
                "departures": trips[:24],
            }
            for i, origin in enumerate(matched):
                for dest in matched[i + 1 :]:
                    key = f"{origin['id']}|{dest['id']}"
                    bucket = pair_hits.setdefault(key, [])
                    if len(bucket) >= limit_per_pair:
                        continue
                    if any(item["route"] == record["route"] for item in bucket):
                        continue
                    bucket.append(record)

    return {
        "source": "Vonter/bmtc-gtfs csv/routes.csv",
        "license_note": "Unofficial BMTC GTFS. Timetables can be approximate.",
        "pair_count": len(pair_hits),
        "pairs": pair_hits,
    }


def main() -> int:
    places = _load_places()
    routes_csv = _download(ROUTES_URL, CACHE / "bmtc_routes.csv")
    network = extract(routes_csv, places)
    OUTPUT.write_text(json.dumps(network, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT} with {network['pair_count']} place pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
