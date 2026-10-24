"""Wardrobe data and outfit combinations built from it.

The Shopping Skeptic only picks from combinations generated here, so it can
never suggest clothes the user doesn't own.
"""

from __future__ import annotations

import json
from pathlib import Path

from colors import delta_e, harmony_report, is_neutral, name_color

WARDROBE_FILE = Path(__file__).parent / "wardrobe.json"

# Rough dress-code level (1 = loungewear, 5 = black tie) by keyword.
OCCASION_FORMALITY = [
    (("wedding", "sangeet", "reception", "gala", "black tie"), 4.5),
    (("interview", "board", "client", "pitch", "conference", "keynote"), 4.0),
    (("office", "work", "meeting", "formal"), 3.5),
    (("festival", "diwali", "eid", "puja", "festive", "mehendi"), 3.5),
    (("date", "dinner", "party", "brunch", "meetup", "event"), 3.0),
    (("college", "casual", "coffee", "shopping", "travel", "airport", "weekend"), 1.5),
    (("gym", "home", "lounge"), 1.0),
]


def load_wardrobe() -> list[dict]:
    items = json.loads(WARDROBE_FILE.read_text())
    for item in items:
        item["color_name"] = name_color(item["hex"])
    return items


def occasion_formality(occasion: str) -> float:
    text = (occasion or "").lower()
    for keywords, level in OCCASION_FORMALITY:
        if any(k in text for k in keywords):
            return level
    return 3.0


def _palette_fit(hex_color: str, palette: list[str]) -> float:
    if is_neutral(hex_color):
        return 0.8
    distance = min(delta_e(hex_color, p) for p in palette) if palette else 40
    return max(0.0, 1 - distance / 45)


def generate_combos(items: list[dict], palette: list[str], occasion: str,
                    exclude_ids: set[str] | None = None, limit: int = 6) -> list[dict]:
    target = occasion_formality(occasion)
    by_cat = {c: [i for i in items if i["category"] == c]
              for c in ("top", "bottom", "dress", "outerwear", "shoes", "accessory")}
    bases = [(t, b) for t in by_cat["top"] for b in by_cat["bottom"]] + [(d,) for d in by_cat["dress"]]

    combos = []
    for base in bases:
        for shoes in by_cat["shoes"]:
            for layer in [None, *by_cat["outerwear"]]:
                pieces = [*base, shoes] + ([layer] if layer else [])
                if exclude_ids and {p["id"] for p in pieces} == exclude_ids:
                    continue
                hexes = [p["hex"] for p in pieces]
                harmony = harmony_report(hexes)
                formality = sum(p["formality"] for p in pieces) / len(pieces)
                fit = sum(_palette_fit(h, palette) for h in hexes) / len(hexes)
                score = (harmony["rule_based_harmony_score"] / 10) * 0.4 \
                    + fit * 0.35 \
                    + max(0, 1 - abs(formality - target) / 2.5) * 0.25
                combos.append({"items": pieces, "harmony": harmony,
                               "formality": round(formality, 1), "score": score})

    combos.sort(key=lambda c: -c["score"])

    # One combo per base piece, so the suggestions aren't six variations of the same top.
    picked, used_bases = [], set()
    for combo in combos:
        base_id = combo["items"][0]["id"]
        if base_id in used_bases:
            continue
        used_bases.add(base_id)
        picked.append(combo)
        if len(picked) >= limit:
            break

    accessory = max(by_cat["accessory"], key=lambda a: _palette_fit(a["hex"], palette), default=None)
    for n, combo in enumerate(picked, 1):
        if accessory:
            combo["items"] = combo["items"] + [accessory]
        combo["id"] = f"C{n}"
        combo["score"] = round(combo["score"] * 10, 1)
    return picked


def describe_items(items: list[dict]) -> str:
    return "\n".join(
        f"- [{i['id']}] {i['name']} ({i['category']}, {i['color_name']} {i['hex']}, "
        f"formality {i['formality']}/5, {', '.join(i['tags'])})"
        for i in items
    )


def describe_combos(combos: list[dict]) -> str:
    return "\n".join(
        f"{c['id']}: " + " + ".join(f"{p['name']} [{p['id']}]" for p in c["items"])
        + f" | {c['harmony']['scheme']}, formality {c['formality']}/5, fit {c['score']}/10"
        for c in combos
    )
