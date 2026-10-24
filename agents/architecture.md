# 🏗️ Architecture & System Design

The **Global Outdoor Event Planner Agent** operates as an autonomous decision engine with deterministic tool calls and evaluation heuristic loops.

---

## 📐 High-Level Workflow Diagram

```text
  ┌──────────────────────────┐
  │   User / Orchestrator    │
  └─────────────┬────────────┘
                │ Target Cities List
                ▼
  ┌──────────────────────────┐
  │  GlobalEventPlannerAgent │
  └─────────────┬────────────┘
                │ Invokes Tool for Each Target
                ▼
  ┌──────────────────────────┐      ┌───────────────────────────┐
  │ fetch_city_weather_tool  ├─────►│  Open-Meteo Geocode API   │
  └─────────────┬────────────┘      └─────────────┬─────────────┘
                │ Coordinates                     │ Lat/Lon
                ▼                                 ▼
  ┌──────────────────────────┐      ┌───────────────────────────┐
  │ Forecast Telemetry Fetch ├─────►│ Open-Meteo Forecast API   │
  └─────────────┬────────────┘      └───────────────────────────┘
                │ Metrics (Temp, Precip, Wind)
                ▼
  ┌──────────────────────────┐
  │  Heuristic Safety Filter │
  └─────────────┬────────────┘
                │ Suitability Decision
                ▼
  ┌──────────────────────────┐
  │ Final Output Aggregator  │
  └──────────────────────────┘
```

---

## 🧱 Component Breakdown

### 1. Agent Orchestrator (`GlobalEventPlannerAgent`)
- Manages execution loops across input target cities.
- Coordinates tool calls, error handling, and state compilation.
- Outputs standardized payload formatting for down-stream integrations.

### 2. Meteorological Telemetry Tool (`fetch_city_weather_tool`)
- Performs two-stage resolution:
  1. **Geocoding:** Translates raw city strings into precise geographic coordinates ($latitude, longitude$).
  2. **Forecast Ingestion:** Pulls active temperature ($2m$), precipitation, wind speeds ($10m$), and weather condition codes.

### 3. Heuristic Decision Engine
Applies threshold checks for outdoor event comfort and structural safety:
- **Temperature ($T$):** $16^\circ\text{C} \le T \le 27^\circ\text{C}$
- **Precipitation ($P$):** $P = 0.0\text{ mm}$
- **Wind Speed ($W$):** $W < 20.0\text{ km/h}$