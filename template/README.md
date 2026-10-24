# 🌍 Global Outdoor Event Planner Agent

An intelligent, multi-tool AI Agent system designed to analyze real-time and forecasted weather telemetry across global cities to determine optimal locations for hosting outdoor events.

Built following open-source agent patterns, this system evaluates meteorological parameters—such as ambient temperature, precipitation risk, wind gusts, and humidity—against customizable safety and comfort heuristics for event production.

---

## 📌 Features

- **Global City Geocoding & Weather Telemetry:** Real-time data retrieval via Open-Meteo API (no API keys required).
- **Multi-Factor Decision Engine:** Assesses temperature, precipitation, and wind speeds against safe event thresholds.
- **Structured Tool Execution:** Follows clean Python agent patterns for tool binding, state orchestration, and schema generation.
- **Modular Architecture:** Designed to easily integrate additional skills like venue discovery, timezone adjustment, and calendar booking.

---

## 🛠️ Project Structure

```text
├── README.md           # Project overview and quickstart
├── architecture.md     # System design and component diagrams
├── skills.md           # Specification of tools and agent competencies
└── plan.md             # Development roadmap and enhancement strategy
```

---

## 🚀 Quickstart

### Prerequisites

- Python 3.9+
- `requests` library

```bash
pip install requests
```

### Running the Agent

Run the main execution script to evaluate candidates across global hubs:

```bash
python weather_agent_node.py
```

---

## 📊 Sample Agent Output

```json
{
    "status": "success",
    "total_analyzed": 5,
    "shortlisted_count": 2,
    "top_candidates": [
        "Tokyo, Japan",
        "San Francisco, United States"
    ],
    "detailed_telemetry": [
        {
            "city": "Tokyo, Japan",
            "temperature_celsius": 19.5,
            "precipitation_mm": 0.0,
            "wind_speed_kmh": 8.2,
            "condition": "Clear / Sunny",
            "outdoor_event_suitable": true,
            "recommendation_reason": "Optimal outdoor conditions: Comfortable temperature, zero rain risk, calm winds."
        }
    ]
}
```

---

## 📜 License

MIT License. Open for community contributions!

## Developer
Sheetal G
Sheetal G

https://linkedin.com/in/techsheetal
