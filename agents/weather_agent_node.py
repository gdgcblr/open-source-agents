import requests
from typing import List, Dict, Any

def fetch_city_weather_and_aqi_tool(city_name: str) -> Dict[str, Any]:
    """
    Tool: Queries global weather and Air Quality telemetry (PM2.5, PM10, US AQI)
    to evaluate outdoor event feasibility and recommend indoor backups if needed.
    """
    # Step 1: Geocoding Lookup
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&language=en&format=json"
    geo_res = requests.get(geo_url).json()
    
    if not geo_res.get("results"):
        return {"city": city_name, "error": "Location metadata lookup failed."}
        
    loc = geo_res["results"][0]
    lat, lon = loc["latitude"], loc["longitude"]
    country_tag = loc.get("country", "Global")

    # Step 2: Weather Telemetry Fetch
    weather_url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m"
    )
    w_data = requests.get(weather_url).json().get("current", {})

    temp = w_data.get("temperature_2m", 0.0)
    precip = w_data.get("precipitation", 0.0)
    wind = w_data.get("wind_speed_10m", 0.0)
    w_code = w_data.get("weather_code", 0)

    # Step 3: Air Quality Telemetry Fetch (Open-Meteo Air Quality API)
    aqi_url = (
        f"https://air-quality-api.open-meteo.com/v1/air-quality?"
        f"latitude={lat}&longitude={lon}&current=us_aqi,pm2_5,pm10"
    )
    aqi_res = requests.get(aqi_url).json()
    aqi_data = aqi_res.get("current", {})

    us_aqi = aqi_data.get("us_aqi", 0)
    pm2_5 = aqi_data.get("pm2_5", 0.0)
    pm10 = aqi_data.get("pm10", 0.0)

    # Synthesis & Evaluation Rules
    condition = "Clear / Sunny" if w_code <= 2 else "Overcast" if w_code <= 3 else "Active Rain"
    
    # AQI Safety Status (US AQI <= 100 is Moderate/Good)
    aqi_safe = us_aqi <= 100 and pm2_5 <= 35.4
    
    # Weather Safety
    weather_safe = (precip == 0.0) and (15.0 <= temp <= 28.0) and (wind < 22.0)
    
    is_outdoor_suitable = weather_safe and aqi_safe

    # Failure Diagnostics & Indoor Backup Suggestions
    failure_reasons = []
    backup_suggestions = []

    if temp < 15.0:
        failure_reasons.append(f"Low Temp ({temp}°C)")
        backup_suggestions.append("Heated Glasshouse / Heated Atrium Pavilion")
    elif temp > 28.0:
        failure_reasons.append(f"High Heat ({temp}°C)")
        backup_suggestions.append("Air-Conditioned Grand Ballroom / Covered Canopy Lounge")

    if precip > 0.0:
        failure_reasons.append(f"Precipitation ({precip} mm)")
        backup_suggestions.append("Indoor Convention Center / Retractable Roof Venue")

    if wind >= 22.0:
        failure_reasons.append(f"High Wind ({wind} km/h)")
        backup_suggestions.append("Enclosed Indoor Auditorium")

    if not aqi_safe:
        failure_reasons.append(f"Unhealthy Air Quality (AQI {us_aqi}, PM2.5 {pm2_5} µg/m³)")
        backup_suggestions.append("Climate-controlled HVAC Enclosed Indoor Arena")

    if is_outdoor_suitable:
        recommendation_reason = f"Ideal: Sunny/Clear, {temp}°C, Calm Winds ({wind}km/h), Good Air Quality (AQI {us_aqi})."
        venue_backup = "No backup needed (Outdoor venue approved)."
    else:
        recommendation_reason = f"Outdoor Unsuitable due to: {', '.join(failure_reasons)}."
        venue_backup = f"Suggested Backup: { ' or '.join(list(set(backup_suggestions))) }"

    return {
        "city": f"{city_name}, {country_tag}",
        "temperature_celsius": temp,
        "precipitation_mm": precip,
        "wind_speed_kmh": wind,
        "us_aqi": us_aqi,
        "pm2_5": pm2_5,
        "pm10": pm10,
        "condition": condition,
        "outdoor_event_suitable": is_outdoor_suitable,
        "recommendation_reason": recommendation_reason,
        "venue_backup_suggestion": venue_backup
    }

class GlobalEventPlannerAgent:
    def __init__(self, target_cities: List[str]):
        self.target_cities = target_cities

    def execute_workflow(self) -> Dict[str, Any]:
        evaluated_reports: List[Dict[str, Any]] = []
        shortlisted_venues: List[str] = []

        for city in self.target_cities:
            report = fetch_city_weather_and_aqi_tool(city)
            evaluated_reports.append(report)
            
            if report.get("outdoor_event_suitable"):
                shortlisted_venues.append(report["city"])

        return {
            "status": "success",
            "total_analyzed": len(self.target_cities),
            "shortlisted_count": len(shortlisted_venues),
            "top_candidates": shortlisted_venues,
            "detailed_telemetry": evaluated_reports
        }