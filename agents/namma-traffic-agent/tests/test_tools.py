"""
test_tools.py - Unit tests for Bengaluru Traffic & Transit Tools
"""

import pytest
from agent.tools import (
    get_route_traffic,
    check_chokepoints,
    get_metro_alternative,
    get_weather_waterlogging_alerts,
    calculate_best_departure_window,
    get_road_repairs_and_hazards
)


def test_get_route_traffic_basic():
    res = get_route_traffic("koramangala", "whitefield", hour=18)
    assert res["status"] == "success"
    assert res["distance_km"] > 10
    assert res["current_travel_time_mins"] > res["off_peak_time_mins"]
    assert "cost_estimates" in res
    assert res["cost_estimates"]["cab_uber_ola_inr"] > 0


def test_get_route_traffic_rain():
    dry_res = get_route_traffic("hsr_layout", "bellandur", hour=18, is_raining=False)
    rain_res = get_route_traffic("hsr_layout", "bellandur", hour=18, is_raining=True)
    assert rain_res["current_travel_time_mins"] >= dry_res["current_travel_time_mins"]


def test_check_chokepoints():
    # Specific bottleneck
    silk = check_chokepoints("silk board")
    assert silk["status"] == "success"
    assert "Silk Board" in silk["junction"]
    
    # All bottlenecks
    all_cp = check_chokepoints("all")
    assert all_cp["status"] == "success"
    assert len(all_cp["chokepoints"]) >= 5


def test_get_metro_alternative():
    res = get_metro_alternative("indiranagar", "whitefield")
    assert res["status"] == "success"
    assert "Whitefield" in res["destination_deboarding_station"]
    assert "Purple" in res["origin_boarding_station"]
    assert res["breakdown"]["total_multimodal_time_mins"] > 0


def test_get_weather_waterlogging_alerts():
    alerts = get_weather_waterlogging_alerts()
    assert alerts["status"] == "success"
    assert alerts["waterlogged_hotspots_count"] >= 3
    assert any("Kadubeesanahalli" in a["location"] for a in alerts["alerts"])


def test_calculate_best_departure_window():
    res = calculate_best_departure_window("koramangala", "whitefield", target_hour=18)
    assert res["status"] == "success"
    assert "golden_departure_window" in res
    assert len(res["schedule_options"]) == 5


def test_get_road_repairs_and_hazards():
    res = get_road_repairs_and_hazards("all")
    assert res["status"] == "success"
    assert res["count"] >= 5
    assert any("Silk Board" in r["name"] for r in res["repairs"])
    assert any("Ecospace" in r["name"] for r in res["repairs"])
