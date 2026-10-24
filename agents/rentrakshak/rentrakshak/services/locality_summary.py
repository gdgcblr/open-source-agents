from __future__ import annotations

import statistics
from collections import defaultdict

from rentrakshak.services.rent_estimator import _load_observations

POPULAR_LOCALITIES = [
    "Koramangala",
    "Indiranagar",
    "HSR Layout",
    "Whitefield",
    "Electronic City",
    "Marathahalli",
    "Bellandur",
    "Hebbal",
]


def popular_locality_cards() -> list[dict]:
    obs = _load_observations()
    by_loc: dict[str, list[int]] = defaultdict(list)
    classifications: dict[str, set[str]] = defaultdict(set)
    for o in obs:
        loc = o.get("locality", "")
        if not loc:
            continue
        by_loc[loc].append(int(o["monthly_rent_inr"]))
        classifications[loc].add(o.get("data_classification", "unknown"))

    cards = []
    for loc in POPULAR_LOCALITIES:
        rents = by_loc.get(loc, [])
        if not rents:
            cards.append(
                {
                    "locality": loc,
                    "rent_min_inr": None,
                    "rent_max_inr": None,
                    "rent_median_inr": None,
                    "comparable_count": 0,
                    "data_note": "No demo comparables yet",
                }
            )
            continue
        cards.append(
            {
                "locality": loc,
                "rent_min_inr": min(rents),
                "rent_max_inr": max(rents),
                "rent_median_inr": int(statistics.median(rents)),
                "comparable_count": len(rents),
                "data_note": "Demo dataset — asking rents, not transactions",
                "classifications": sorted(classifications[loc]),
            }
        )
    return cards
