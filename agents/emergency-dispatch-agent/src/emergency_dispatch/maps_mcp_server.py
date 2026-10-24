import os
from datetime import datetime, timezone

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("emergency-dispatch-maps")

PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


def get_headers(field_mask: str) -> dict[str, str]:
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY is not configured.")
    return {
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": field_mask,
        "Content-Type": "application/json",
    }


@mcp.tool()
def search_nearby_hospitals(
    latitude: float,
    longitude: float,
    radius_meters: int = 5000,
) -> dict:
    """Find nearby hospitals using Google Places API."""

    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Invalid GPS coordinates.")
    if not 1 <= radius_meters <= 50000:
        raise ValueError("Radius must be between 1 and 50000 meters.")

    response = httpx.post(
        PLACES_URL,
        headers=get_headers(
            "places.id,places.displayName,places.formattedAddress,places.location"
        ),
        json={
            "includedTypes": ["hospital"],
            "maxResultCount": 10,
            "rankPreference": "DISTANCE",
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": latitude,
                        "longitude": longitude,
                    },
                    "radius": radius_meters,
                }
            },
        },
        timeout=15,
    )
    response.raise_for_status()

    return {
        "source": "Google Places API",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "hospitals": response.json().get("places", []),
        "capacity_verified": False,
        "clinical_capabilities_verified": False,
    }


@mcp.tool()
def compute_traffic_aware_route(
    origin_latitude: float,
    origin_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
) -> dict:
    """Get a driving route and traffic-aware travel estimate."""

    for lat, lng in (
        (origin_latitude, origin_longitude),
        (destination_latitude, destination_longitude),
    ):
        if not -90 <= lat <= 90 or not -180 <= lng <= 180:
            raise ValueError("Invalid GPS coordinates.")

    response = httpx.post(
        ROUTES_URL,
        headers=get_headers(
            "routes.duration,routes.staticDuration,routes.distanceMeters"
        ),
        json={
            "origin": {
                "location": {
                    "latLng": {
                        "latitude": origin_latitude,
                        "longitude": origin_longitude,
                    }
                }
            },
            "destination": {
                "location": {
                    "latLng": {
                        "latitude": destination_latitude,
                        "longitude": destination_longitude,
                    }
                }
            },
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
        },
        timeout=20,
    )
    response.raise_for_status()

    routes = response.json().get("routes", [])
    return {
        "status": "route_found" if routes else "no_route_found",
        "source": "Google Routes API",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "routes": routes,
    }


if __name__ == "__main__":
    mcp.run()
