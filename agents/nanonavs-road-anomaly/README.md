# NanoNavs Road Intelligence

> An autonomous AI agent that detects, classifies, and reports road surface anomalies (potholes, cracks, speed bumps, debris) using multi-sensor fusion with optional Gemini AI-enhanced incident narratives.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Urban road infrastructure deteriorates continuously, but manual inspection is slow, expensive, and inconsistent. Potholes, cracks, and surface depressions cause vehicle damage, accidents, and commuter delays — especially in rapidly growing cities like Bengaluru where road maintenance cannot keep pace with traffic growth.
- **Intended Users**: Municipal road maintenance teams, urban planning agencies, fleet operators, ride-sharing companies, and civic-tech developers building smart-city applications.

### Key Features
- **Multi-Sensor Fusion**: Combines accelerometer (vibration), GPS (geolocation), and acoustic (impact noise) data streams for high-confidence anomaly detection.
- **Deterministic Detection Engine**: Threshold-based signal processing with sliding-window analysis — no cloud dependency, works entirely offline.
- **Intelligent Classification**: Distinguishes between potholes, speed bumps, cracks, surface depressions, and debris using sensor signature patterns.
- **Severity-Weighted Scoring**: Calculates a 0–100 Road Quality Score with severity-based penalty weighting.
- **AI-Enhanced Reporting** *(optional)*: When a Gemini API key is configured, generates natural-language incident narratives for municipal teams.
- **Interactive Dashboard**: Streamlit-based UI with sensor visualisation, anomaly mapping, and downloadable reports.
- **Synthetic Data Generator**: Built-in Bengaluru route simulator with configurable anomaly injection for reproducible demonstrations.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Core**: Custom deterministic signal-processing engine (no external ML framework required)
- **AI Enhancement**: Google Gemini 2.5 Flash via `google-genai` SDK (optional — agent works fully without it)
- **Dashboard**: Streamlit
- **Data Processing**: Pandas, NumPy
- **Testing**: pytest
- **Configuration**: python-dotenv

---

## Architecture & Data Flow

```
[Vehicle Sensors]          [Synthetic Data Generator]
  (Accelerometer,     OR     (sensor_data.py)
   GPS, Microphone)              |
        |                        |
        v                        v
  ┌─────────────────────────────────────┐
  │        SensorFrame Stream           │
  │  (models.py — GPS, Accel, Audio)    │
  └──────────────┬──────────────────────┘
                 │
                 v
  ┌─────────────────────────────────────┐
  │      Anomaly Detector               │
  │  (detector.py)                      │
  │  • Sliding-window analysis          │
  │  • Threshold-based classification   │
  │  • Acoustic fusion boost            │
  │  • Speed-adjusted sensitivity       │
  │  • Cooldown de-duplication          │
  └──────────────┬──────────────────────┘
                 │
                 v
  ┌─────────────────────────────────────┐
  │      Report Generator               │
  │  (report_generator.py)              │
  │  • Road Quality Score (0–100)       │
  │  • Severity distribution            │
  │  • Deterministic summary            │
  │  • Optional Gemini AI narrative     │
  └──────────────┬──────────────────────┘
                 │
        ┌────────┴────────┐
        v                 v
  [CLI Output]     [Streamlit Dashboard]
  (main.py)        (app.py)
   • Terminal        • Sensor charts
     report          • Anomaly map
   • JSON export     • Detection table
   • CSV analysis    • Downloadable reports
```

---

## Prerequisites

Before running this project, ensure you have:
- **Python 3.10+** (tested on 3.10, 3.11, 3.12)
- **pip** (or uv) package manager
- *(Optional)* A [Google AI Studio](https://aistudio.google.com/) API key for Gemini-enhanced reports

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/nanonavs-road-anomaly
   ```

2. **Set up the virtual environment and install dependencies:**
   ```bash
   python -m venv .venv

   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Configure Environment Variables (optional):**
   ```bash
   # Linux/macOS:
   cp .env.example .env
   # Windows PowerShell:
   Copy-Item .env.example .env
   ```
   Edit `.env` and add your Gemini API key if you want AI-enhanced narratives. The agent works completely without it.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | No | *None* | Google AI Studio API key for Gemini-enhanced reports |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Gemini model identifier |
| `TEMPERATURE` | No | `0.2` | LLM temperature for narrative generation |
| `NANONAVS_LOG_LEVEL` | No | `info` | Logging verbosity |
| `NANONAVS_REPORT_DIR` | No | `reports` | Directory for saved report files |

> **Note:** The agent is fully functional without any API keys. Gemini integration only adds natural-language narratives to the reports.

---

## How to Run

### Command-Line Interface (CLI)

```bash
# Run interactive demo with default route (Silk Board → Marathahalli)
python main.py

# Run demo with a specific Bengaluru route
python main.py --route hebbal

# Run with more sensor frames for higher fidelity
python main.py --route electronic-city --frames 500

# Output results as JSON
python main.py --json

# Save reports to the reports/ directory
python main.py --save

# Analyse a custom CSV sensor data file
python main.py --csv sensor_data.csv

# Generate sample CSV data files for all routes
python main.py --generate-sample-data
```

### Streamlit Dashboard

```bash
streamlit run app.py
```

This launches an interactive web dashboard where you can:
- Select routes and configure sensor parameters
- Tune detection sensitivity in real time
- Visualise accelerometer, speed, and acoustic data
- View anomalies on an interactive map
- Download reports in JSON and text formats

---

## Example Input & Output

### Example CLI Input
```bash
python main.py --route silk-board --frames 200
```

### Example CLI Output
```
╔══════════════════════════════════════════════════════════════╗
║        🛣️  NanoNavs Road Intelligence Agent  🛣️              ║
║     Autonomous Road Anomaly Detection & Classification      ║
╚══════════════════════════════════════════════════════════════╝

📍 Route: Silk Board → Marathahalli (ORR)
   Outer Ring Road stretch — notoriously congested and pothole-prone
   Distance: 11.8 km

📡 Generating 200 sensor frames (10 Hz sampling rate)...
   ✓ 200 frames generated
   ✓ 16 ground-truth anomalies injected

🔍 Running anomaly detection pipeline...
   ✓ 14 anomalies detected

── Detected Anomalies ──────────────────────────────────────
   1. 🟠 pothole              | high      | 78% conf | 0.62g | 📍 (12.920199, 77.629812)
   2. 🟡 crack                | moderate  | 52% conf | 0.18g | 📍 (12.925468, 77.639053)
   3. 🔴 pothole              | critical  | 91% conf | 0.85g | 📍 (12.932571, 77.651277)
   ...

═══ NanoNavs Incident Report ═══
Report ID: RPT-A1B2C3D4
Route: Silk Board → Marathahalli (ORR)
Distance: 11.8 km
Road Quality Score: 62.4/100

By Severity:
  🟢 low: 3
  🟡 moderate: 5
  🟠 high: 4
  🔴 critical: 2

⚠️ CAUTION: Significant surface degradation. Reduce speed advised.
```

---

## How to Test

Run the full automated test suite:

```bash
# From the project directory:
cd agents/nanonavs-road-anomaly
pytest tests/ -v
```

The test suite covers:
- **Data model** serialisation and validation (5 tests)
- **Anomaly detector** accuracy, classification, and edge cases (7 tests)
- **Sensor data generator** consistency and reproducibility (7 tests)
- **Report generator** quality scoring and output formatting (5 tests)
- **End-to-end pipeline** across all routes (2 tests)
- **Edge cases**: single frames, zero distance, no acoustic data, extreme counts (4 tests)

All tests run without any API keys or network access.

---

## Known Limitations

- **Synthetic data only**: The current demonstration uses synthetic sensor data. Real-world deployment would require hardware integration with vehicle-mounted sensors (OBD-II accelerometers, GPS modules, microphones).
- **Threshold calibration**: Detection thresholds are empirically set and may need tuning for different vehicle types, tyre pressures, and road surface materials.
- **No persistent storage**: Detected anomalies are not stored in a database. A production system would need a spatial database (e.g., PostGIS) for historical trend analysis.
- **Gemini rate limits**: When using the optional Gemini AI integration, free-tier API keys are subject to rate limits (approximately 60 requests/minute).
- **GPS accuracy**: Synthetic GPS data includes realistic HDOP jitter but does not model urban canyon effects or tunnel signal loss.
- **Tested on**: Windows 11 with Python 3.12. Linux and macOS should work but are not formally verified.

---

## Security & Privacy Considerations

- **Secrets Handling**: API keys are loaded exclusively from environment variables via `python-dotenv`. The `.env` file is excluded by `.gitignore`. Only `.env.example` (with placeholder values) is committed.
- **Data Privacy**: Synthetic demonstration data uses public Bengaluru road coordinates. No personal data, vehicle identifiers, or real telemetry is collected or transmitted.
- **External Services**: When Gemini AI is enabled, anonymised anomaly statistics (type, severity, GPS coordinates) are sent to the Google Gemini API for narrative generation. No personally identifiable information is included.
- **No Arbitrary Execution**: The agent does not execute shell commands, modify files outside its report directory, or access resources beyond its declared dependencies.

---

## Future Improvements

- [ ] Integrate real OBD-II / smartphone accelerometer data via Bluetooth or USB
- [ ] Add PostGIS spatial database for historical anomaly tracking
- [ ] Implement time-series anomaly detection using ML (isolation forest or autoencoder)
- [ ] Support local models via Ollama for fully offline AI narratives
- [ ] Add multi-vehicle fleet aggregation and consensus detection
- [ ] Build a mobile companion app for crowd-sourced road quality reporting
- [ ] Add OpenStreetMap integration for road segment identification
- [ ] Implement A* routing that avoids high-anomaly-density segments

---

## License

*This project is contributed under the repository's open-source license.*
