from __future__ import annotations

import json
import statistics
from datetime import date, datetime
from pathlib import Path

from rentrakshak.config import package_root
from rentrakshak.models.schemas import RentEstimateResult

MIN_COMPARABLES = 2
STALE_DAYS = 540


def _load_observations() -> list[dict]:
    path = package_root() / "data" / "rent_comparables.json"
    with path.open(encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("observations", [])


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def estimate_bengaluru_rent(
    locality: str,
    bhk: str | None = None,
    furnishing: str | None = None,
    property_type: str | None = None,
) -> RentEstimateResult:
    obs = _load_observations()
    loc_n = _norm(locality)
    matches = [o for o in obs if _norm(o.get("locality")) == loc_n]

    if bhk:
        bhk_n = _norm(bhk).replace(" ", "")
        matches = [o for o in matches if _norm(o.get("bhk")).replace(" ", "") == bhk_n]

    if furnishing:
        matches = [o for o in matches if _norm(o.get("furnishing")) == _norm(furnishing)]

    if property_type:
        matches = [o for o in matches if _norm(o.get("property_type")) == _norm(property_type)]

    limitations: list[str] = []
    if not matches:
        return RentEstimateResult(
            locality=locality,
            bhk=bhk,
            furnishing=furnishing,
            property_type=property_type,
            comparable_count=0,
            rent_min_inr=None,
            rent_median_inr=None,
            rent_max_inr=None,
            data_classification="none",
            newest_observation_date=None,
            oldest_observation_date=None,
            methodology="No matching comparables in local dataset.",
            limitations=[
                "Insufficient data — do not treat any LLM guess as a market estimate.",
            ],
            sufficient_data=False,
        )

    rents = [int(o["monthly_rent_inr"]) for o in matches if o.get("monthly_rent_inr", 0) > 0]
    if len(rents) < MIN_COMPARABLES:
        limitations.append(
            f"Only {len(rents)} comparable(s) found; need at least {MIN_COMPARABLES} for a range."
        )
        classifications = {o.get("data_classification", "unknown") for o in matches}
        return RentEstimateResult(
            locality=locality,
            bhk=bhk,
            furnishing=furnishing,
            property_type=property_type,
            comparable_count=len(rents),
            rent_min_inr=None,
            rent_median_inr=None,
            rent_max_inr=None,
            data_classification=",".join(sorted(classifications)),
            newest_observation_date=_date_extreme(matches, max),
            oldest_observation_date=_date_extreme(matches, min),
            methodology="Comparable median with minimum sample threshold.",
            limitations=limitations,
            sufficient_data=False,
        )

    today = date.today()
    for o in matches:
        dc = o.get("date_collected")
        if dc:
            try:
                d = datetime.strptime(dc, "%Y-%m-%d").date()
                if (today - d).days > STALE_DAYS:
                    limitations.append(f"Some observations are older than {STALE_DAYS} days.")
            except ValueError:
                limitations.append("Invalid date format in dataset entry.")

    classifications = {o.get("data_classification", "unknown") for o in matches}
    if "illustrative_sample" in classifications:
        limitations.append(
            "Dataset includes illustrative samples — estimate is for demonstration, not a live market quote."
        )

    limitations.append("Figures reflect asking rents in dataset, not verified transaction prices.")

    return RentEstimateResult(
        locality=locality,
        bhk=bhk,
        furnishing=furnishing,
        property_type=property_type,
        comparable_count=len(rents),
        rent_min_inr=min(rents),
        rent_median_inr=int(statistics.median(rents)),
        rent_max_inr=max(rents),
        data_classification=",".join(sorted(classifications)),
        newest_observation_date=_date_extreme(matches, max),
        oldest_observation_date=_date_extreme(matches, min),
        methodology=(
            "Filter local JSON comparables by locality and optional BHK/furnishing/type; "
            "report min/median/max of monthly_rent_inr."
        ),
        limitations=limitations,
        sufficient_data=True,
    )


def _date_extreme(matches: list[dict], fn) -> str | None:
    dates = []
    for o in matches:
        dc = o.get("date_collected")
        if dc:
            try:
                dates.append(datetime.strptime(dc, "%Y-%m-%d").date())
            except ValueError:
                continue
    if not dates:
        return None
    return fn(dates).isoformat()
