# 🧰 Agent Skills & Capabilities Specification

This document details the functional tools and skills integrated into the Global Outdoor Event Planner Agent ecosystem.


## 🧬 Existing Skills

### `fetch_city_weather_tool`

- **Purpose:** Resolves geographic coordinates for a given city and queries current weather metrics.
- **Input Parameters:**
  - `city_name` (*string*, required): Name of the target city (e.g., "Tokyo", "Bengaluru").
- **Output Schema:**
  - `city` (*string*): Resolved name and country.
  - `temperature_celsius` (*float*): Air temperature at 2m height.
  - `precipitation_mm` (*float*): Rain/snowfall volume in mm.
  - `wind_speed_kmh` (*float*): Surface wind velocity in km/h.
  - `condition` (*string*): Human-readable weather summary.
  - `outdoor_event_suitable` (*boolean*): Boolean indicator of safety/comfort compliance.
  - `recommendation_reason` (*string*): Explicit justification for decision.

---

## 🔮 Planned Skills (Enhancements)

### 1. `venue_search_tool`
- **Description:** Queries local venue APIs (e.g., Google Maps Places) to find outdoor parks, rooftop terraces, or amphitheaters in approved candidate cities.
- **Inputs:** `city_name`, `event_type`, `min_capacity`.

### 2. `air_quality_index_tool`
- **Description:** Checks particulate matter ($PM_{2.5}$, $PM_{10}$) and AQI ratings to ensure outdoor safety during wildfire or high-pollution advisories.
- **Inputs:** `latitude`, `longitude`.

### 3. `timezone_event_scheduler_tool`
- **Description:** Normalizes event schedules across multiple candidate global time zones to ensure optimal local lighting hours (e.g., daylight times).
- **Inputs:** `city_name`, `target_utc_time`.