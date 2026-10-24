import json
import requests
from typing import List, Dict, Any

# Custom Tool Definition
def get_city_weather(city_name: str) -> Dict[str, Any]:
    """
    Fetches real-time weather metrics for a specified city using Open-Meteo API.
    
    Args:
        city_name (str): Name of the city (e.g., 'Tokyo', 'Sydney', 'Barcelona')
        
    Returns:
        dict: Weather data including temperature, precipitation probability, and outdoor event suitability.
    """
    # Step 1: Geocoding lookup for city coordinates
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&language=en&format=json"
    geo_res = requests.get(geo_url).json()
    
    if not geo_res.get("results"):
        return {"city": city_name, "error": "City location not found"}
        
    location = geo_res["results"][0]
    lat, lon = location["latitude"], location["longitude"]
    country = location.get("country", "")

    # Step 2: Fetch current weather & 1-day forecast metrics
    weather_url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m"
    )
    w_res = requests.get(weather_url).json()
    current = w_res.get("current", {})

    temp_c = current.get("temperature_2m", 0)
    precip_mm = current.get("precipitation", 0)
    wind_kmh = current.get("wind_speed_10m", 0)
    
    # Weather code mapping for general conditions
    w_code = current.get("weather_code", 0)
    condition = "Clear/Sunny" if w_code <= 2 else "Cloudy" if w_code <= 3 else "Rain/Showers"
    
    # Decision logic for hosting outdoor events
    is_outdoor_suitable = (precip_mm == 0) and (15 <= temp_c <= 28) and (wind_kmh < 25)

    return {
        "city": f"{city_name}, {country}",
        "temperature_celsius": temp_c,
        "precipitation_mm": precip_mm,
        "wind_speed_kmh": wind_kmh,
        "condition": condition,
        "outdoor_event_suitable": is_outdoor_suitable,
        "recommendation_reason": (
            "Ideal weather: Moderate temperature, clear skies, low wind."
            if is_outdoor_suitable
            else "Sub-optimal for outdoor events due to temperature, wind, or rain risk."
        )
    }

# Agent Evaluator Orchestrator
def run_event_location_agent(cities: List[str]) -> Dict[str, Any]:
    """
    Executes the weather checker tool across multiple global cities 
    and determines the best host candidate for an outdoor event.
    """
    results = []
    recommended_cities = []

    print("🤖 Agent Initialized: Checking global weather for outdoor event planning...\n")
    
    for city in cities:
        # Tool call
        weather_data = get_city_weather(city)
        results.append(weather_data)
        
        if weather_data.get("outdoor_event_suitable"):
            recommended_cities.append(weather_data["city"])

    return {
        "all_reports": results,
        "top_recommendations": recommended_cities,
        "summary": f"Evaluated {len(cities)} global locations. {len(recommended_cities)} city/cities passed outdoor venue criteria."
    }