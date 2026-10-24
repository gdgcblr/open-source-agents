"""Real-time Google Maps and Weather extraction tools."""

import os
from typing import Any, Dict, List
import requests

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")


def fetch_google_routes(origin: str, destination: str) -> List[Dict[str, Any]]:
    """Fetches primary and alternative routes from Google Maps with real-time traffic."""
    if not GOOGLE_MAPS_API_KEY:
        raise ValueError("GOOGLE_MAPS_API_KEY environment variable is not set.")

    endpoint = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin,
        "destination": destination,
        "alternatives": "true",
        "departure_time": "now",
        "traffic_model": "best_guess",
        "key": GOOGLE_MAPS_API_KEY,
    }

    resp = requests.get(endpoint, params=params, timeout=12)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "OK":
        raise RuntimeError(f"Google Maps API error: {data.get('status')} - {data.get('error_message', 'No details')}")

    parsed_routes = []
    for idx, route in enumerate(data.get("routes", [])):
        summary = route.get("summary", f"Alternative {idx + 1}")
        leg = route["legs"][0]
        normal_duration = leg.get("duration", {}).get("value", 0)  # seconds
        traffic_duration = leg.get("duration_in_traffic", {}).get("value", normal_duration)
        delay_sec = max(0, traffic_duration - normal_duration)

        # Extract major road checkpoints for weather sampling
        waypoints = []
        for step in leg.get("steps", []):
            end_loc = step.get("end_location", {})
            instructions = step.get("html_instructions", "")
            waypoints.append({
                "lat": end_loc.get("lat"),
                "lng": end_loc.get("lng"),
                "instruction": instructions
            })

        parsed_routes.append({
            "route_id": idx + 1,
            "summary": summary,
            "distance_km": round(leg.get("distance", {}).get("value", 0) / 1000.0, 2),
            "normal_duration_min": round(normal_duration / 60.0, 1),
            "traffic_duration_min": round(traffic_duration / 60.0, 1),
            "delay_min": round(delay_sec / 60.0, 1),
            "sample_waypoints": waypoints[::max(1, len(waypoints) // 4)],  # sample ~4 key checkpoints
            "all_steps": [s.get("html_instructions") for s in leg.get("steps", [])[:8]]
        })

    return parsed_routes


def fetch_route_weather(lat: float, lng: float) -> Dict[str, Any]:
    """Retrieves real-time precipitation and rain intensity via Open-Meteo."""
    endpoint = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lng,
        "current": ["precipitation", "rain", "weather_code", "wind_speed_10m"],
    }
    try:
        resp = requests.get(endpoint, params=params, timeout=8)
        resp.raise_for_status()
        current = resp.json().get("current", {})
        rain_mm = current.get("rain", 0.0)
        precip_mm = current.get("precipitation", 0.0)

        # Classify precipitation severity
        if precip_mm >= 7.6:
            severity = "Heavy Downpour / Risk of Localized Waterlogging"
        elif precip_mm >= 2.5:
            severity = "Moderate Rain"
        elif precip_mm > 0.0:
            severity = "Light Drizzle"
        else:
            severity = "Clear / No Rain"

        return {
            "rain_mm": rain_mm,
            "precipitation_mm": precip_mm,
            "severity": severity,
            "wind_speed_kmh": current.get("wind_speed_10m", 0.0),
        }
    except Exception as exc:
        return {"error": str(exc), "severity": "Weather data unavailable"}
