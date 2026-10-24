from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@lru_cache(maxsize=1)
def load_places() -> list[dict]:
    payload = json.loads((FIXTURES / "places.json").read_text(encoding="utf-8"))
    return payload["places"]


def all_place_names() -> list[str]:
    names: list[str] = []
    for place in load_places():
        names.append(place["name"])
        names.extend(place.get("aliases") or [])
    return names


def resolve_place(text: str | None) -> dict | None:
    if not text:
        return None
    needle = " ".join(text.strip().lower().split())
    if not needle:
        return None
    for place in load_places():
        candidates = [place["id"], place["name"].lower(), *(place.get("aliases") or [])]
        if needle in {item.lower() for item in candidates}:
            return place
    for place in load_places():
        if place["id"] in needle or place["name"].lower() in needle:
            return place
        if any(alias.lower() in needle for alias in place.get("aliases") or []):
            return place
    return None
