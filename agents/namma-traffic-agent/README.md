# 🚦 Namma Bengaluru Traffic Copilot

> Real-time Bengaluru traffic intelligence, multimodal transit optimization, and bottleneck bypass agent.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Google GenAI SDK](https://img.shields.io/badge/Google%20GenAI-Gemini%202.5-orange.svg)](https://ai.google.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Built for the **FORK. BUILD. MERGE.** initiative under **Road to DevFest 2026** by **GDG Cloud Bengaluru**.

---

## 📌 Problem Statement

Bengaluru commuters lose an estimated **250+ hours per year** in gridlock. Major tech corridors—such as the Outer Ring Road (Silk Board to Marathahalli/Hebbal), Old Airport Road, and Whitefield—suffer from severe bottlenecks, sudden monsoon rain waterlogging at railway underpasses, and chaotic surge pricing on ride-hailing apps.

Standard navigation apps often give raw point-to-point times without contextual advice:
- *Should I take Namma Metro instead of a cab during peak rush hour?*
- *When is the golden departure window to avoid a 60-minute delay?*
- *Is Central Silk Board or Tin Factory currently impassable?*
- *Are key underpasses flooded after recent rains?*

**Namma Traffic Copilot** is a domain-specialized AI agent designed to bridge this gap by combining LLM tool-calling reasoning (powered by Google Gemini 2.5 Flash) with local transit knowledge and deterministic fallbacks.

---

## 🏛️ Architecture Overview

```mermaid
flowchart TD
    User["Commuter (CLI / Web Dashboard)"] --> Agent["NammaTrafficAgent Core"]
    
    subgraph Reasoning Engine
        Agent -->|Checks API Key| Router{"API Key Present?"}
        Router -->|Yes| Gemini["Google GenAI (Gemini 2.5 Flash)"]
        Router -->|No / Offline| Heuristics["Deterministic Local Transit Engine"]
    end
    
    subgraph Specialized Bengaluru Transit Tools
        Gemini & Heuristics --> T1["get_route_traffic()"]
        Gemini & Heuristics --> T2["check_chokepoints()"]
        Gemini & Heuristics --> T3["get_metro_alternative()"]
        Gemini & Heuristics --> T4["get_weather_waterlogging_alerts()"]
        Gemini & Heuristics --> T5["calculate_best_departure_window()"]
    end
    
    subgraph Bengaluru Transit Knowledge Base
        T1 & T2 & T3 & T4 & T5 --> KB["Curated Transit Geospatial Database\n(ORR Corridors, Metro Stations, Underpasses)"]
    end
    
    T1 & T2 & T3 & T4 & T5 --> Synthesis["Commute Report & Smart Advice"]
    Synthesis --> Output["Rich Terminal Table / Web UI Cards"]
```

---

## ⚡ Key Features

- **Multimodal Metro vs Cab Comparator:** Directly compares road travel times and surge taxi fares against Namma Metro (Purple, Green, and Yellow Lines), highlighting saved minutes and rupees.
- **Bengaluru Chokepoint Intelligence:** Live congestion scores, delay estimates, and internal bypass routes for Silk Board, Tin Factory, Hebbal Flyover, Marathahalli Bridge, Ecospace ORR, and Goraguntepalya.
- **Monsoon & Underpass Alerts:** Tracks waterlogging risks in notorious low-lying underpasses (Kadubeesanahalli, Okalipuram, Panathur RUB).
- **Golden Departure Optimizer:** Computes congestion curves across a 3-hour window to recommend the single best time to leave.
- **100% Out-of-the-Box Reproducibility:** Operates with full functionality in local heuristic mode even without an external API key; enhanced by Gemini 2.5 Flash when `GEMINI_API_KEY` is supplied.

---

## 🛠️ Prerequisites

- Python 3.10 or higher
- Optional: Google Gemini API Key (`GEMINI_API_KEY`) from [Google AI Studio](https://aistudio.google.com/)

---

## 🚀 Quick Start

### 1. Clone & Navigate to Project

```bash
git clone https://github.com/<your-username>/open-source-ai.git
cd open-source-ai/agents/namma-traffic-agent
```

*(Or if running directly from scratch directory:)*
```bash
cd C:\Users\ShaikAli\.gemini\antigravity\scratch\namma-traffic-agent
```

### 2. Install Dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Configure Environment (Optional)

```bash
cp .env.example .env
# Edit .env and paste your GEMINI_API_KEY (optional)
```

---

## 💻 Usage

### Option A: Interactive CLI & Rich Terminal Dashboard

Run a single natural language query:
```bash
python main.py "How is traffic from Koramangala to Whitefield at 6 PM?"
```

Simulate heavy monsoon rain impact:
```bash
python main.py "How is traffic from HSR to Bellandur?" --rain
```

Inspect specific chokepoints:
```bash
python main.py "Is Silk Board jammed?"
```

Check waterlogged underpasses:
```bash
python main.py "Are there any flooded roads or underpass alerts?"
```

Launch interactive conversational mode:
```bash
python main.py
```

### Option B: Interactive Web Dashboard & REST API

Launch the local web server:
```bash
python server.py
```
Open your browser at **[http://localhost:8000](http://localhost:8000)** to view the visual dashboard with quick-action commute cards, live congestion meters, and the AI Copilot.

---

## 📊 Sample Terminal Output

```
  _   _                                _____            __  __ _        
 | \ | | __ _ _ __ ___  _ __ ___   __ |_   _| __ __ _ / _|/ _(_) ___   
 |  \| |/ _` | '_ ` _ \| '_ ` _ \ / _` || || '__/ _` | |_| |_| |/ __|  
 | |\  | (_| | | | | | | | | | | | (_| || || | | (_| |  _|  _| | (__   
 |_| \_|\__,_|_| |_| |_|_| |_| |_|\__,_||_||_|  \__,_|_| |_| |_|\___|  

🚦 Real-time Bengaluru Traffic Copilot & Multimodal Commute Optimizer
Powered by Google GenAI (Gemini 2.5 Flash) + Local Transit Intelligence

● Mode: local-heuristic-engine (Running in reproducible local mode)
⚡ Tools Invocations: get_route_traffic, get_metro_alternative, calculate_best_departure_window

               🚗 Commute Overview: Koramangala ➡️ Whitefield               
┌─────────────────────┬────────────────────────────────────────────────────┐
│ Metric              │ Details                                            │
├─────────────────────┼────────────────────────────────────────────────────┤
│ Distance            │ 19.1 km                                            │
│ Current Travel Time │ 130 mins                                           │
│ Off-Peak Duration   │ 52 mins                                            │
│ Traffic Congestion  │ 🔴 Heavy Gridlock (Expect bumper-to-bumper delays) │
│ Est. Auto Fare      │ ₹315                                               │
│ Est. Cab Fare       │ ₹832 (Surge: 1.6x)                                 │
└─────────────────────┴────────────────────────────────────────────────────┘

                     🚇 Namma Metro Multimodal Alternative                     
┌──────────────────┬───────────────────────────────────────────────┬──────────┐
│ Stage            │ Station / Mode                                │ Time     │
├──────────────────┼───────────────────────────────────────────────┼──────────┤
│ First Mile       │ South End Circle (Green Line, 4.5 km away)    │ ~23 mins │
│ Metro Train Ride │ Interchange: Majestic (Nadaprabhu Kempegowda) │ 50 mins  │
│ Last Mile        │ Whitefield (Kadugodi) (Purple Line, 0.0 km)   │ ~5 mins  │
│ Total Time       │ Door-to-door                                  │ 78 mins  │
│ Fare             │ Metro ₹57 + Auto                              │ ₹87      │
└──────────────────┴───────────────────────────────────────────────┴──────────┘

┌────────────────────── 🤖 Namma Copilot Recommendation ──────────────────────┐
│  🚗 Bengaluru Commute Assessment: Koramangala ➡️ Whitefield                 │
│  • Estimated Road Travel Time: 130 minutes (Off-peak: 52 mins)             │
│  • Congestion: 🔴 Heavy Gridlock (Expect bumper-to-bumper delays)          │
│                                                                             │
│  🚇 Multimodal Alternative (Namma Metro):                                   │
│  • Total Door-to-Door Time: ~78 mins (vs 130 mins road cab)                │
│  • Cost: ₹87 (Saves ₹745 vs cab surge)                                     │
│  • Verdict: 🚇 Highly Recommended: Take Namma Metro                        │
│                                                                             │
│  ⏱️ Smart Departure Advice: Leaving at 16:00 hrs can save you up to 63      │
│  minutes compared to peak rush at 17:00 hrs!                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Repository Structure

```
agents/namma-traffic-agent/
├── README.md              # Comprehensive documentation and guide
├── requirements.txt       # Dependencies manifest
├── .env.example           # Sanitized environment variable template
├── .gitignore             # Git ignore rules
├── main.py                # Rich CLI entrypoint & interactive REPL
├── server.py              # FastAPI web server and REST API
├── agent/
│   ├── __init__.py        # Package exports
│   ├── core.py            # NammaTrafficAgent implementation & Gemini tool calling
│   ├── knowledge.py       # Bengaluru transit dataset (corridors, hubs, choke points)
│   └── tools.py           # 5 specialized transit intelligence tools
├── web/
│   └── index.html         # Modern responsive web dashboard (dark mode)
└── tests/
    ├── test_agent.py      # Tests for agent execution and intent handling
    └── test_tools.py      # Tests for all 5 specialized traffic tools
```

---

## 🧪 Testing & Verification

Run the automated test suite using `pytest`:

```bash
python -m pytest tests/
```

Expected output:
```
tests/test_agent.py ....                                                 [ 40%]
tests/test_tools.py ......                                               [100%]
============================= 10 passed in 0.20s ==============================
```

---

## ⚠️ Known Limitations & Assumptions

1. **Traffic Modeling:** Traffic delays and multipliers are calibrated against Bengaluru's historical peak-hour commute distributions (Morning 8:30-11:30 AM, Evening 5:00-9:00 PM). Live external API integrations (Google Maps / TomTom Traffic API) can be hooked up for dynamic GPS probe inputs.
2. **Yellow Line Metro:** The Yellow Line (RV Road to Bommasandra / Electronic City) schedule estimates are modeled on trial-run and projected frequency.

---

## 🗺️ Roadmap & Extensions

- [ ] Direct integration with Karnataka Open Data / Bengaluru Traffic Police (BTP) live twitter/feed advisories.
- [ ] BMTC Vajra / Vayu Vajra Airport bus real-time GPS schedule tracking.
- [ ] Integration into WhatsApp / Telegram bot via Twilio or FastAPI webhook.

---

## 📜 License & Community

Licensed under the **MIT License**. Created with ❤️ for **GDG Cloud Bengaluru**'s **FORK. BUILD. MERGE. (Road to DevFest 2026)**.
