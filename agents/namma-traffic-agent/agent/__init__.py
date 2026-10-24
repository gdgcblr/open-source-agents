"""Namma Bengaluru Traffic Copilot Package."""

from .core import NammaTrafficAgent
from .tools import (
    get_route_traffic,
    check_chokepoints,
    get_metro_alternative,
    get_weather_waterlogging_alerts,
    calculate_best_departure_window,
    get_bmtc_bus_details,
    get_bengaluru_live_weather,
    get_road_repairs_and_hazards
)

__all__ = [
    "NammaTrafficAgent",
    "get_route_traffic",
    "check_chokepoints",
    "get_metro_alternative",
    "get_weather_waterlogging_alerts",
    "calculate_best_departure_window",
    "get_bmtc_bus_details",
    "get_bengaluru_live_weather",
    "get_road_repairs_and_hazards"
]
