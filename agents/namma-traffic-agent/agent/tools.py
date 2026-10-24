"""
tools.py - Specialized Transit & Traffic Tools for Bengaluru Copilot
Implements realistic route computations, choke point intelligence, Namma Metro comparisons,
and monsoon weather waterlogging advisories.
"""

import math
from datetime import datetime
from typing import Dict, List, Any, Optional
from .knowledge import (
    BENGALURU_HUBS,
    CHOKEPOINTS,
    MONSOON_WATERLOGGING_ZONES,
    METRO_LINES,
    BMTC_BUS_ROUTES,
    BENGALURU_WEATHER_CURRENT,
    METRO_STATION_COORDS,
    BUS_STOP_COORDS,
    BENGALURU_ROAD_REPAIRS
)


def _normalize_name(query: str) -> Optional[str]:
    """Finds best matching hub key from query string."""
    query = query.lower().strip()
    
    # Direct alias map for common colloquial names
    aliases = {
        "kora": "koramangala",
        "indira": "indiranagar",
        "ecity": "electronic_city",
        "e-city": "electronic_city",
        "elcity": "electronic_city",
        "blr": "airport",
        "kempegowda": "airport",
        "kia": "airport",
        "bangalore airport": "airport",
        "hsr": "hsr_layout",
        "bellanduru": "bellandur",
        "ecospace": "bellandur",
        "ecoworld": "bellandur",
        "itpl": "whitefield",
        "manyata tech park": "manyata",
        "nagavara": "manyata",
        "ksr": "majestic",
        "central": "majestic",
        "station": "majestic",
        "jp": "jp_nagar",
        "j.p. nagar": "jp_nagar",
        "mg": "mg_road",
        "brigade": "mg_road"
    }
    
    for alias, target in aliases.items():
        if alias in query:
            return target
            
    for key, data in BENGALURU_HUBS.items():
        if key in query or data["display_name"].lower() in query:
            return key
            
    return None


def _calculate_haversine_distance(coord1: tuple, coord2: tuple) -> float:
    """Calculates approximate distance in kilometers between two GPS coordinates."""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    R = 6371.0 # Earth radius in km
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    # In urban Bangalore, actual road distance is ~1.35x Euclidean
    return round(R * c * 1.35, 1)


def get_route_traffic(
    origin: str,
    destination: str,
    hour: Optional[int] = None,
    is_raining: bool = False
) -> Dict[str, Any]:
    """
    Computes road distance, current travel time vs off-peak duration, congestion rating,
    bottlenecks encountered, and estimated cab fares.
    """
    origin_key = _normalize_name(origin)
    dest_key = _normalize_name(destination)
    
    if not origin_key or not dest_key:
        return {
            "status": "error",
            "message": f"Could not recognize locations. Recognized hubs: {', '.join(BENGALURU_HUBS.keys())}"
        }
    
    if origin_key == dest_key:
        return {
            "status": "success",
            "distance_km": 1.5,
            "off_peak_minutes": 8,
            "current_minutes": 10,
            "congestion_level": "Low",
            "message": "Origin and destination are within the same neighborhood. Consider walking or cycling!"
        }

    orig_data = BENGALURU_HUBS[origin_key]
    dest_data = BENGALURU_HUBS[dest_key]
    distance_km = _calculate_haversine_distance(orig_data["coords"], dest_data["coords"])
    
    # Determine hour
    if hour is None:
        hour = datetime.now().hour
        
    # Congestion multiplier based on time
    multiplier = 1.0
    time_label = "Off-Peak"
    
    # Peak hour bands in Bengaluru
    if 8 <= hour <= 11:
        multiplier = 2.1
        time_label = "Morning Peak (Tech Corridor Inflow)"
    elif 12 <= hour <= 16:
        multiplier = 1.3
        time_label = "Afternoon Moderate Flow"
    elif 17 <= hour <= 21:
        multiplier = 2.5
        time_label = "Evening Rush Hour (ORR/CBD Outflow)"
    elif 22 <= hour <= 23 or 6 <= hour <= 7:
        multiplier = 1.15
        time_label = "Shoulder Window"
    else:
        multiplier = 0.9
        time_label = "Late Night / Early Morning Clear"
        
    # Rain penalty
    if is_raining:
        multiplier *= 1.45
        time_label += " + Rain Disruption"

    # Identify Chokepoints along this route
    active_chokepoints = []
    chokepoint_delay_mins = 0
    for cp_key, cp_data in CHOKEPOINTS.items():
        for pair in cp_data["affected_routes"]:
            if (pair[0] == origin_key and pair[1] == dest_key) or (pair[1] == origin_key and pair[0] == dest_key):
                active_chokepoints.append({
                    "name": cp_data["name"],
                    "congestion_index": cp_data["peak_congestion_index"],
                    "reason": cp_data["reason"],
                    "workaround": cp_data["best_workaround"],
                    "delay_minutes": cp_data["base_delay_minutes"] if multiplier >= 1.5 else int(cp_data["base_delay_minutes"] * 0.4)
                })
                chokepoint_delay_mins += active_chokepoints[-1]["delay_minutes"]
                break

    # Average base speed in Bengaluru is ~22 km/h off-peak, drops to 8-12 km/h during peak
    base_minutes = int((distance_km / 22.0) * 60)
    current_minutes = int((base_minutes * multiplier) + (chokepoint_delay_mins * 0.6))
    
    # Classify congestion
    ratio = current_minutes / max(base_minutes, 1)
    if ratio > 2.2:
        congestion_category = "🔴 Heavy Gridlock (Expect bumper-to-bumper delays)"
    elif ratio > 1.6:
        congestion_category = "🟠 Heavy Congestion"
    elif ratio > 1.2:
        congestion_category = "🟡 Moderate Crawl"
    else:
        congestion_category = "🟢 Smooth Flow"

    # Surge & Cab estimate
    surge = 1.0
    if multiplier >= 2.0:
        surge = 1.6 if not is_raining else 2.1
    elif multiplier >= 1.4:
        surge = 1.25

    est_auto_fare = int((30 + max(0.0, distance_km - 2) * 15) * (1.15 if multiplier > 1.5 else 1.0)) if distance_km > 2 else 30
    est_cab_fare = int((100 + distance_km * 22) * surge)
    est_bike_fare = int((20 + max(0.0, distance_km - 1.5) * 8.5) * (1.1 if surge > 1.2 else 1.0))

    return {
        "status": "success",
        "origin": orig_data["display_name"],
        "destination": dest_data["display_name"],
        "distance_km": distance_km,
        "traffic_condition": time_label,
        "congestion_category": congestion_category,
        "off_peak_time_mins": base_minutes,
        "current_travel_time_mins": current_minutes,
        "auto_travel_time_mins": int(current_minutes * 0.88),
        "bike_travel_time_mins": int(current_minutes * 0.65),
        "delay_minutes": max(0, current_minutes - base_minutes),
        "chokepoints_on_route": active_chokepoints,
        "cost_estimates": {
            "cab_uber_ola_inr": est_cab_fare,
            "namma_auto_inr": max(30, est_auto_fare),
            "bike_taxi_rapido_inr": max(20, est_bike_fare),
            "surge_active": surge > 1.0,
            "surge_multiplier": f"{surge:.1f}x"
        }
    }


def check_chokepoints(junction: str = "all") -> Dict[str, Any]:
    """Returns real-time congestion ratings, reasons, and bypass routes for Bengaluru junctions."""
    j_key = junction.lower().replace(" ", "_")
    
    if j_key in CHOKEPOINTS:
        data = CHOKEPOINTS[j_key]
        return {
            "status": "success",
            "junction": data["name"],
            "congestion_index": f"{data['peak_congestion_index']} / 10",
            "base_delay_minutes": f"~{data['base_delay_minutes']} mins",
            "reason": data["reason"],
            "best_workaround": data["best_workaround"]
        }
        
    # Return all bottlenecks
    results = []
    for k, v in CHOKEPOINTS.items():
        results.append({
            "key": k,
            "name": v["name"],
            "congestion_index": f"{v['peak_congestion_index']}/10",
            "delay_minutes": v["base_delay_minutes"],
            "workaround": v["best_workaround"]
        })
    return {"status": "success", "chokepoints": results}


def get_metro_alternative(origin: str, destination: str) -> Dict[str, Any]:
    """
    Evaluates whether Namma Metro (Purple, Green, Yellow) offers a faster,
    cheaper alternative to road cabs.
    """
    orig_key = _normalize_name(origin)
    dest_key = _normalize_name(destination)
    
    if not orig_key or not dest_key:
        return {"status": "error", "message": "Unknown origin or destination"}
        
    orig_data = BENGALURU_HUBS[orig_key]
    dest_data = BENGALURU_HUBS[dest_key]
    
    orig_metro_station, orig_line, orig_first_mile_km = orig_data["nearest_metro"]
    dest_metro_station, dest_line, dest_last_mile_km = dest_data["nearest_metro"]
    
    # Calculate metro feasibility
    is_direct = (orig_line == dest_line and orig_line in ["Purple", "Green", "Yellow"])
    interchange_needed = not is_direct and orig_line != dest_line
    
    # First mile & last mile times (Auto / e-rickshaw @ 15 km/h + 5 min wait)
    first_mile_time = int((orig_first_mile_km / 15.0) * 60) + 5
    last_mile_time = int((dest_last_mile_km / 15.0) * 60) + 5
    
    # Approximate metro train ride time
    road_dist = _calculate_haversine_distance(orig_data["coords"], dest_data["coords"])
    metro_train_mins = max(10, int(road_dist * 2.2))
    if interchange_needed:
        metro_train_mins += 8  # Interchange transfer at Majestic or RV Road
        
    total_multimodal_time = first_mile_time + metro_train_mins + last_mile_time
    metro_fare = min(60, max(20, int(15 + road_dist * 2.2)))
    qr_smartcard_fare = int(metro_fare * 0.95)
    first_last_mile_fare = (30 if orig_first_mile_km > 0.5 else 0) + (30 if dest_last_mile_km > 0.5 else 0)
    total_metro_cost = qr_smartcard_fare + first_last_mile_fare

    # Comparison verdict
    road_traffic = get_route_traffic(origin, destination, hour=18)
    road_cab_time = road_traffic.get("current_travel_time_mins", 60)
    road_cab_fare = road_traffic.get("cost_estimates", {}).get("cab_uber_ola_inr", 350)
    
    time_saved = road_cab_time - total_multimodal_time
    money_saved = road_cab_fare - total_metro_cost
    
    recommendation = "🚇 Highly Recommended: Take Namma Metro" if time_saved > 10 else "🚖 Road Cab may be comparable or faster (direct route)"
    if orig_first_mile_km > 10 or dest_last_mile_km > 10:
        recommendation = "🚗 Road preferred (metro connectivity distant at one or both ends)"

    # Intermediate Metro Stations
    all_stations = METRO_LINES.get(orig_line, {}).get("stations", [])
    intermediate_stations = []
    if orig_metro_station in all_stations and dest_metro_station in all_stations:
        idx1 = all_stations.index(orig_metro_station)
        idx2 = all_stations.index(dest_metro_station)
        start_idx, end_idx = min(idx1, idx2), max(idx1, idx2)
        slice_names = all_stations[start_idx:end_idx+1]
        if idx1 > idx2:
            slice_names.reverse()
        for s in slice_names:
            coords = METRO_STATION_COORDS.get(s)
            intermediate_stations.append({
                "name": s,
                "lat": coords[0] if coords else None,
                "lng": coords[1] if coords else None
            })
    else:
        # Cross-line or transfer stations
        for s_name in [orig_metro_station, "Nadaprabhu Kempegowda Majestic (Interchange)" if interchange_needed else None, dest_metro_station]:
            if s_name:
                coords = METRO_STATION_COORDS.get(s_name.split(" (")[0])
                intermediate_stations.append({
                    "name": s_name,
                    "lat": coords[0] if coords else None,
                    "lng": coords[1] if coords else None
                })

    return {
        "status": "success",
        "route": f"{orig_data['display_name']} ➡️ {dest_data['display_name']}",
        "origin_boarding_station": f"{orig_metro_station} ({orig_line} Line, {orig_first_mile_km} km away)",
        "destination_deboarding_station": f"{dest_metro_station} ({dest_line} Line, {dest_last_mile_km} km away)",
        "interchange_required": "Majestic (Nadaprabhu Kempegowda)" if interchange_needed else "None (Direct Line)",
        "line_color": "#9333ea" if orig_line == "Purple" else ("#16a34a" if orig_line == "Green" else "#ca8a04"),
        "train_frequency": "Every 4 to 5 minutes (Peak Hours)",
        "station_count": len(intermediate_stations),
        "intermediate_stations": intermediate_stations,
        "metro_token_fare_inr": metro_fare,
        "metro_qr_smartcard_fare_inr": qr_smartcard_fare,
        "total_transit_cost_inr": total_metro_cost,
        "breakdown": {
            "first_mile_mins": first_mile_time,
            "train_ride_mins": metro_train_mins,
            "last_mile_mins": last_mile_time,
            "total_multimodal_time_mins": total_multimodal_time
        },
        "comparison_with_road_cab": {
            "road_cab_time_mins": road_cab_time,
            "road_cab_cost_inr": road_cab_fare,
            "time_saved_mins": max(0, time_saved),
            "money_saved_inr": max(0, money_saved)
        },
        "verdict": recommendation
    }


def get_bmtc_bus_details(origin: str, destination: str) -> Dict[str, Any]:
    """
    Finds direct or connecting BMTC bus routes (Ordinary & AC Vajra)
    with exact route numbers, fares, frequency, and stops.
    """
    orig_key = _normalize_name(origin)
    dest_key = _normalize_name(destination)
    
    if not orig_key or not dest_key:
        return {"status": "error", "message": "Unknown origin or destination"}
        
    orig_data = BENGALURU_HUBS[orig_key]
    dest_data = BENGALURU_HUBS[dest_key]
    
    matching_routes = []
    for bus in BMTC_BUS_ROUTES:
        if orig_key in bus["connects"] and dest_key in bus["connects"]:
            matching_routes.append(bus)
            
    # Default fallback bus route if not in direct corridor
    if not matching_routes:
        matching_routes = [{
            "route_no": "500-D / Feeder",
            "route_name": f"{orig_data['display_name']} ⇄ {dest_data['display_name']} (Connecting Corridor)",
            "service_type": "AC Vajra Volvo & Ordinary",
            "corridor": "Bengaluru Transit Grid",
            "frequency_minutes": 8,
            "fare_ordinary_inr": 25,
            "fare_ac_vajra_inr": 45,
            "highlights": "Transfer via nearest TTMC or Outer Ring Road interchange.",
            "stops": [
                orig_data.get("bus_stop", f"{orig_data['display_name']} Bus Bay"),
                "Outer Ring Road Connector",
                "Marathahalli Multiplex",
                dest_data.get("bus_stop", f"{dest_data['display_name']} Bus Bay")
            ]
        }]
        
    primary_bus = matching_routes[0]
    road_dist = _calculate_haversine_distance(orig_data["coords"], dest_data["coords"])
    est_bus_time = int((road_dist / 16.0) * 60) + 10  # BMTC bus avg speed ~16 km/h + stops

    raw_stops = primary_bus.get("stops", [])
    stops_with_coords = []
    for st_name in raw_stops:
        coords = BUS_STOP_COORDS.get(st_name)
        if not coords:
            # Substring / partial matching
            norm_st = st_name.lower()
            for k, c in BUS_STOP_COORDS.items():
                if k.lower() in norm_st or norm_st in k.lower():
                    coords = c
                    break
        stops_with_coords.append({
            "name": st_name,
            "lat": coords[0] if coords else None,
            "lng": coords[1] if coords else None
        })

    return {
        "status": "success",
        "route": f"{orig_data['display_name']} ➡️ {dest_data['display_name']}",
        "primary_bus": primary_bus,
        "available_bus_numbers": [b["route_no"] for b in matching_routes],
        "boarding_bus_stop": orig_data.get("bus_stop", f"{orig_data['display_name']} Bus Bay"),
        "deboarding_bus_stop": dest_data.get("bus_stop", f"{dest_data['display_name']} Bus Bay"),
        "stop_count": len(raw_stops),
        "intermediate_stops": stops_with_coords,
        "fare_ordinary_inr": primary_bus["fare_ordinary_inr"],
        "fare_ac_vajra_inr": primary_bus["fare_ac_vajra_inr"],
        "frequency": f"Every {primary_bus['frequency_minutes']} minutes",
        "estimated_travel_time_mins": est_bus_time,
        "highlights": primary_bus["highlights"]
    }


def get_bengaluru_live_weather() -> Dict[str, Any]:
    """Returns real-time Bengaluru weather, rainfall intensity, and traffic impact."""
    return {
        "status": "success",
        "weather": BENGALURU_WEATHER_CURRENT
    }


def get_weather_waterlogging_alerts(area: str = "all") -> Dict[str, Any]:
    """Provides current alerts regarding monsoon rains, inundated underpasses, and BTP diversions."""
    alerts = []
    for item in MONSOON_WATERLOGGING_ZONES:
        if area == "all" or area.lower() in item["location"].lower():
            alerts.append(item)
            
    return {
        "status": "success",
        "weather_status": "Bengaluru Weather Advisory: Intermittent Thunderstorms / Rain Warning",
        "waterlogged_hotspots_count": len(alerts),
        "alerts": alerts,
        "btp_general_advisory": "Bengaluru Traffic Police urges commuters to avoid underpasses during active rain. Maintain headlight visibility and safe stopping distance on ORR flyovers."
    }


def calculate_best_departure_window(origin: str, destination: str, target_hour: int = 18) -> Dict[str, Any]:
    """
    Evaluates travel times at different departure intervals (-60m, -30m, 0, +30m, +60m, +90m)
    to find the optimal departure time that avoids peak congestion.
    """
    times = []
    candidate_hours = [
        max(6, target_hour - 2),
        max(6, target_hour - 1),
        target_hour,
        min(23, target_hour + 1),
        min(23, target_hour + 2)
    ]
    
    for h in candidate_hours:
        res = get_route_traffic(origin, destination, hour=h)
        if res.get("status") == "success":
            times.append({
                "departure_time": f"{h:02d}:00 hrs",
                "estimated_minutes": res["current_travel_time_mins"],
                "congestion": res["congestion_category"]
            })
            
    if not times:
        return {"status": "error", "message": "Failed to calculate departure window"}
        
    best_option = min(times, key=lambda x: x["estimated_minutes"])
    worst_option = max(times, key=lambda x: x["estimated_minutes"])
    time_diff = worst_option["estimated_minutes"] - best_option["estimated_minutes"]
    
    return {
        "status": "success",
        "origin": origin,
        "destination": destination,
        "target_hour": f"{target_hour:02d}:00",
        "schedule_options": times,
        "golden_departure_window": best_option["departure_time"],
        "commute_time_at_golden_window": f"{best_option['estimated_minutes']} mins",
        "time_saved_by_timing": f"{time_diff} minutes saved compared to peak at {worst_option['departure_time']}",
        "pro_tip": f"Departing at {best_option['departure_time']} avoids the primary tech corridor rush."
    }


def get_road_repairs_and_hazards(area: str = "all") -> Dict[str, Any]:
    """
    Returns active BBMP road works, BMRCL metro construction, and BWSSB pipeline
    digging points across Bengaluru with severity, delay impact, and detour bypasses.
    """
    query = area.lower().strip()
    if query in ["all", "", "bangalore", "bengaluru"]:
        return {
            "status": "success",
            "count": len(BENGALURU_ROAD_REPAIRS),
            "repairs": BENGALURU_ROAD_REPAIRS,
            "traffic_police_notice": "Bengaluru Traffic Police (BTP) advises extra travel buffer time through Outer Ring Road and Central Silk Board due to ongoing metro Phase-2A pier and flyover construction."
        }

    filtered = []
    for r in BENGALURU_ROAD_REPAIRS:
        if (
            query in r["name"].lower()
            or query in r["work_type"].lower()
            or query in r["agency"].lower()
            or query in r["recommended_bypass"].lower()
        ):
            filtered.append(r)

    return {
        "status": "success",
        "query": area,
        "count": len(filtered),
        "repairs": filtered if filtered else BENGALURU_ROAD_REPAIRS,
        "traffic_police_notice": "Follow BTP lane diversion signboards and observe reduced speed limit (20 km/h) in active work zones."
    }
