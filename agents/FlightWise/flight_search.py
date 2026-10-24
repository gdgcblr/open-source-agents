from datetime import date
from typing import Any

from .flight_ranking import PRIORITY_WEIGHTS, rank_flights

_SAMPLE_FARES_INR = (4500, 5200, 6300, 7100, 8500, 9600, 11000, 12800)
_SAMPLE_FLIGHTS = (
    ("IndiGo", "6E", "06:10", 2.2, 0),
    ("Air India Express", "IX", "07:35", 2.4, 0),
    ("Akasa Air", "QP", "09:20", 2.5, 0),
    ("Air India", "AI", "11:05", 2.3, 0),
    ("IndiGo", "6E", "13:40", 4.8, 1),
    ("Air India", "AI", "15:15", 5.1, 1),
    ("SpiceJet", "SG", "18:25", 6.0, 1),
    ("Vistara", "UK", "21:10", 7.2, 2),
)
_SUPPORTED_PRIORITIES = tuple(PRIORITY_WEIGHTS)


def _validate_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a valid date in YYYY-MM-DD format.") from None


def _make_mock_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None,
    passengers: int,
) -> list[dict[str, Any]]:
    trip_multiplier = 1.8 if return_date else 1.0
    flights = []
    for index, (airline, code, departure_time, one_way_duration, stops) in enumerate(
        _SAMPLE_FLIGHTS
    ):
        fare = _SAMPLE_FARES_INR[index]
        total_price = round(fare * trip_multiplier * passengers)
        flight = {
            "id": f"DEMO-{code}-{index + 1:02d}",
            "airline": airline,
            "flight_number": f"{code}{100 + index * 13}",
            "origin": origin.strip().upper(),
            "destination": destination.strip().upper(),
            "departure_date": departure_date,
            "return_date": return_date,
            "departure_time": departure_time,
            "outbound_duration_hours": one_way_duration,
            "return_duration_hours": one_way_duration if return_date else None,
            "duration_hours": round(one_way_duration * (2 if return_date else 1), 1),
            "outbound_stops": stops,
            "return_stops": stops if return_date else None,
            "passengers": passengers,
            "price_per_passenger": round(fare * trip_multiplier),
            "total_price": total_price,
            "currency": "INR",
            "checked_bags_included": (1 if index in (0, 2, 3, 5, 7) else 0)
            if index != 6
            else None,
            "carry_on_included": None if index == 6 else index != 4,
            "source": "synthetic_mock",
        }
        flights.append(flight)
    return flights


def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    passengers: int = 1,
    budget: float | None = None,
    currency: str = "INR",
    checked_bags: int = 0,
    carry_on_required: bool = False,
    priority: str = "balanced",
) -> dict[str, Any]:
    """Search synthetic demo flights and return the five best matches.

    This provider-neutral result shape is intended to remain stable when a live
    flight-search provider replaces the mock implementation.
    """
    try:
        if not origin.strip() or not destination.strip():
            raise ValueError("Origin and destination are required.")
        if origin.strip().casefold() == destination.strip().casefold():
            raise ValueError("Origin and destination must be different.")
        outbound = _validate_date(departure_date, "Departure date")
        if return_date:
            inbound = _validate_date(return_date, "Return date")
            if inbound < outbound:
                raise ValueError("Return date cannot be before the departure date.")
        if not 1 <= passengers <= 9:
            raise ValueError("Passenger count must be between 1 and 9.")
        if budget is not None and budget <= 0:
            raise ValueError("Budget must be greater than zero.")
        if not 0 <= checked_bags <= 10:
            raise ValueError("Checked bags must be between 0 and 10.")
        if currency.upper() != "INR":
            raise ValueError("The mock flight search currently supports INR only.")
        if priority not in _SUPPORTED_PRIORITIES:
            raise ValueError(
                "Priority must be balanced, cheapest, fastest, or fewest_stops."
            )
    except (AttributeError, TypeError, ValueError) as error:
        return {"status": "error", "message": str(error)}

    flights = _make_mock_flights(
        origin, destination, departure_date, return_date, passengers
    )
    results = rank_flights(
        flights,
        budget=budget,
        priority=priority,
        checked_bags=checked_bags,
        carry_on_required=carry_on_required,
    )
    return {
        "status": "success",
        "source": "synthetic_mock",
        "disclaimer": (
            "Demo only: these synthetic sample fares and schedules are not live, "
            "verified, or bookable. Baggage details may be unknown."
        ),
        "query": {
            "origin": origin.strip().upper(),
            "destination": destination.strip().upper(),
            "departure_date": departure_date,
            "return_date": return_date,
            "trip_type": "round_trip" if return_date else "one_way",
            "passengers": passengers,
            "budget": budget,
            "currency": "INR",
            "checked_bags": checked_bags,
            "carry_on_required": carry_on_required,
            "priority": priority,
        },
        "results": results,
    }
