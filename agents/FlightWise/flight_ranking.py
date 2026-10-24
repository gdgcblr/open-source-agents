from typing import Any


PRIORITY_WEIGHTS = {
    "balanced": {"price": 0.40, "duration": 0.25, "stops": 0.20, "baggage": 0.15},
    "cheapest": {"price": 0.65, "duration": 0.15, "stops": 0.10, "baggage": 0.10},
    "fastest": {"price": 0.25, "duration": 0.50, "stops": 0.15, "baggage": 0.10},
    "fewest_stops": {"price": 0.25, "duration": 0.15, "stops": 0.50, "baggage": 0.10},
}


def _relative_score(value: float, lowest: float, highest: float) -> float:
    if highest == lowest:
        return 100.0
    return 100.0 * (highest - value) / (highest - lowest)


def _stop_score(stops: int) -> float:
    if stops == 0:
        return 100.0
    if stops == 1:
        return 60.0
    return 25.0


def _baggage_score(
    flight: dict[str, Any], checked_bags: int, carry_on_required: bool
) -> float | None:
    scores = []
    if checked_bags:
        allowance = flight["checked_bags_included"]
        scores.append(50.0 if allowance is None else (100.0 if allowance >= checked_bags else 0.0))
    if carry_on_required:
        allowance = flight["carry_on_included"]
        scores.append(50.0 if allowance is None else (100.0 if allowance else 0.0))
    return sum(scores) / len(scores) if scores else None


def rank_flights(
    flights: list[dict[str, Any]],
    *,
    budget: float | None,
    priority: str,
    checked_bags: int,
    carry_on_required: bool,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Rank normalized flight records; lower prices and shorter journeys score higher."""
    if not flights:
        return []
    if priority not in PRIORITY_WEIGHTS:
        raise ValueError(f"Unsupported ranking priority: {priority}")

    prices = [flight["total_price"] for flight in flights]
    durations = [flight["duration_hours"] for flight in flights]
    weights = PRIORITY_WEIGHTS[priority]
    ranked = []

    for flight in flights:
        price_score = (
            max(0.0, 100.0 * (budget - flight["total_price"]) / budget)
            if budget is not None
            else _relative_score(flight["total_price"], min(prices), max(prices))
        )
        duration_score = _relative_score(flight["duration_hours"], min(durations), max(durations))
        stops = [flight["outbound_stops"]]
        if flight["return_stops"] is not None:
            stops.append(flight["return_stops"])
        stop_score = sum(_stop_score(value) for value in stops) / len(stops)
        baggage_score = _baggage_score(flight, checked_bags, carry_on_required)

        components = {
            "price": round(price_score, 1),
            "duration": round(duration_score, 1),
            "stops": round(stop_score, 1),
            "baggage": round(baggage_score, 1) if baggage_score is not None else None,
        }
        active_weights = {
            name: weight
            for name, weight in weights.items()
            if name != "baggage" or baggage_score is not None
        }
        total_weight = sum(active_weights.values())
        score = sum(
            components[name] * weight for name, weight in active_weights.items()
        ) / total_weight

        result = dict(flight)
        result["score"] = round(score, 1)
        result["score_breakdown"] = components
        result["budget_status"] = (
            "over_budget"
            if budget is not None and flight["total_price"] > budget
            else "within_budget"
            if budget is not None
            else "not_specified"
        )
        ranked.append(result)

    ranked.sort(
        key=lambda flight: (
            flight["budget_status"] == "over_budget",
            -flight["score"],
            flight["total_price"],
        )
    )
    for position, flight in enumerate(ranked[:limit], start=1):
        flight["rank"] = position
    return ranked[:limit]
