"""Mini digital wardrobe + deterministic outfit-combination generator.

The Shopping Skeptic agent picks alternatives ONLY from candidates generated
here, so it can never invent clothes the user doesn't own.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

from .color_engine import delta_e, harmony_report, is_neutral, name_color

DATA = Path(__file__).parent / "data" / "wardrobe.json"

OCCASION_FORMALITY = [
    (("wedding", "sangeet", "reception", "gala", "black tie"), 4.5),
    (("interview", "board", "client", "pitch", "conference talk", "keynote"), 4.0),
    (("office", "work", "meeting", "formal"), 3.5),
    (("festival", "diwali", "eid", "puja", "festive", "mehendi"), 3.5),
    (("date", "dinner", "party", "brunch", "meetup", "devfest", "event"), 3.0),
    (("college", "casual", "coffee", "shopping", "travel", "airport", "weekend"), 1.5),
    (("gym", "home", "lounge"), 1.0),
]


def load_wardrobe() -> list[dict]:
    items = json.loads(DATA.read_text())
    for it in items:
        it["color_name"] = name_color(it["hex"])
    return items


def occasion_formality(occasion: str) -> float:
    o = (occasion or "").lower()
    for keys, level in OCCASION_FORMALITY:
        if any(k in o for k in keys):
            return level
    return 3.0


def _palette_fit(hex_color: str, palette: list[str]) -> float:
    if is_neutral(hex_color):
        return 0.8
    d = min(delta_e(hex_color, p) for p in palette) if palette else 40
    return max(0.0, 1 - d / 45)


def generate_combos(items: list[dict], palette: list[str], occasion: str,
                    exclude_ids: set[str] | None = None, limit: int = 6) -> list[dict]:
    target = occasion_formality(occasion)
    by = {c: [i for i in items if i["category"] == c] for c in
          ("top", "bottom", "dress", "outerwear", "shoes", "accessory")}
    bases = [(t, b) for t in by["top"] for b in by["bottom"]] + [(d,) for d in by["dress"]]

    combos = []
    for base in bases:
        for shoes in by["shoes"]:
            for layer in [None] + by["outerwear"]:
                pieces = [*base, shoes] + ([layer] if layer else [])
                ids = {p["id"] for p in pieces}
                if exclude_ids and ids == exclude_ids:
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
    # Diversity: don't return six combos built on the same base piece.
    picked, used_bases = [], {}
    for c in combos:
        base_id = c["items"][0]["id"]
        if used_bases.get(base_id, 0) >= 1:
            continue
        used_bases[base_id] = used_bases.get(base_id, 0) + 1
        picked.append(c)
        if len(picked) >= limit:
            break

    # Add one accessory that fits the palette best to each combo.
    for c in picked:
        acc = max(by["accessory"], key=lambda a: _palette_fit(a["hex"], palette), default=None)
        if acc:
            c["items"] = c["items"] + [acc]
    for i, c in enumerate(picked, 1):
        c["id"] = f"C{i}"
        c["score"] = round(c["score"] * 10, 1)
    return picked


def describe_items(items: list[dict]) -> str:
    return "\n".join(f"- [{i['id']}] {i['name']} ({i['category']}, {i['color_name']} {i['hex']}, "
                     f"formality {i['formality']}/5, {', '.join(i['tags'])})" for i in items)


def describe_combos(combos: list[dict]) -> str:
    lines = []
    for c in combos:
        names = " + ".join(f"{p['name']} [{p['id']}]" for p in c["items"])
        lines.append(f"{c['id']}: {names} | scheme: {c['harmony']['scheme']}, "
                     f"formality {c['formality']}/5, fit score {c['score']}/10")
    return "\n".join(lines)
