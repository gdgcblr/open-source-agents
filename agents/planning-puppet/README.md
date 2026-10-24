# Planning Puppet 🎉

> A GenAI-powered event planning concierge that helps you organise weddings, birthday parties, and community events — with intelligent budget breakdowns, reverse-engineered timelines, vendor checklists, curated Pinterest inspiration, Google Maps venue search, and a built-in LLM-as-a-Judge quality evaluator.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Planning an event from scratch is overwhelming. Hosts must juggle budgets, vendor bookings, timelines, venues, and aesthetic decisions simultaneously — often without professional guidance.
- **Intended Users**: Individuals planning personal celebrations (weddings, birthdays) and community organisers running festivals, town-hall events, or local gatherings who want structured, AI-driven planning support without hiring an expensive coordinator.

### Key Features
- **Smart Budget Breakdown**: Line-item percentage allocations tailored to the event type (wedding, birthday, or community), with per-guest spend metrics and money-saving tips.
- **Reverse-Engineered Timeline**: Four-phase milestone plans counting backwards from the event date, including a granular hour-by-hour day-of schedule.
- **Vendor Checklist with Due Diligence Questions**: Per-vendor questions to ask before signing contracts, plus recommended booking deadlines by category.
- **Pinterest Inspiration Links**: Curated Markdown-formatted Pinterest search URLs for mood boards, floral layouts, table settings, and colour palettes — matched to the selected aesthetic theme.
- **Google Maps Venue Recommendations**: Real-world venue search using the Google Maps Places API, returning curated banquet halls, resorts, and gardens with live ratings, review counts, and direct Google Maps location URLs.
- **LLM-as-a-Judge Evaluator**: After every agent response, a secondary Gemini call scores the plan 1–5 across Event Type Alignment, Budget Correctness, Timeline Feasibility, and Tone & Empathy — returning a structured JSON verdict.
- **Multi-turn Conversation**: Full session memory powered by ADK's `InMemorySessionService`; follow-up questions naturally refine the plan.
- **Multiple Interfaces**: Interactive Terminal CLI (`main.py`), Streamlit Web UI (`app.py`), and ADK Web UI (`adk web`).

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework**: [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) v1.x
- **Models**: `gemini-3.1-flash-lite`, `gemini-3.8-flash` (via Google AI Studio)
- **External APIs / Tools**: Google Gemini API (agent + evaluator), Google Maps Places API (venue searches), Pinterest (search URL generation — no API key required)
- **Key Libraries**: `google-adk`, `google-genai`, `googlemaps`, `streamlit`, `python-dotenv`, `rich`

---

## Architecture & Data Flow

```text
[User Input (CLI / Streamlit / ADK Web)]
        │
        ▼
[ADK Runner + InMemorySessionService]
        │
        ▼
[PlanningPuppet LlmAgent  ──  Gemini Flash]
        │
        ├──► calculate_budget_breakdown()    → Line items, per-guest spend, tips
        ├──► generate_event_timeline()       → Phased milestones + day-of schedule
        ├──► get_vendor_checklist()          → Vendor list, questions, deadlines
        ├──► generate_pinterest_inspiration()→ Themed Pinterest search links
        └──► search_event_venues()           → Google Maps Places API venue locations
        │
        ▼
[Synthesised Event Plan with Clickable Map Links]
        │
        ▼
[LLM-as-a-Judge Evaluator  ──  Gemini Flash]
        │
        ▼
[Structured JSON: scores / feedback / pass-fail verdict]
        │
        ▼
[Rich CLI Output  or  Streamlit Web UI]
```

---

## Prerequisites

- Python 3.10 or higher
- pip package manager
- A **Google AI Studio API key** — free tier available at [aistudio.google.com](https://aistudio.google.com/app/apikey)
- *(Optional)* A **Google Maps API key** — for live Places API searches (curated fallback links provided if omitted)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/planning-puppet
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv

   # Windows (PowerShell):
   .\.venv\Scripts\activate

   # Linux / macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   # Windows:
   Copy-Item .env.example .env

   # Linux / macOS:
   cp .env.example .env
   ```
   Open `.env` in your editor and set `GEMINI_API_KEY` to your Google AI Studio key.

---

## Configuration & Environment Variables

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `GEMINI_API_KEY` | ✅ Yes | *None* | Google AI Studio / Vertex AI API key |
| `GOOGLE_MAPS_API_KEY` | No | *None* | Google Maps Places API key for live venue search (fallback provided if unset) |
| `MODEL_NAME` | No | `gemini-3.1-flash-lite` | Primary LLM model for the agent (e.g. `gemini-3.1-flash-lite`, `gemini-3.8-flash`) |
| `EVALUATOR_MODEL` | No | `MODEL_NAME` | LLM model for the evaluator (can differ) |
| `ENABLE_EVALUATOR` | No | `true` | Set to `false` to disable quality scoring |
| `LOG_LEVEL` | No | `info` | Logging verbosity |

---

## How to Run

### Option A – Streamlit Web UI (Recommended)
```bash
streamlit run app.py
```
Launches an interactive multi-turn chat UI in your browser with sidebar controls, preset demo buttons, clickable Google Maps links, and expandable quality reports.

### Option B – Interactive Terminal CLI
```bash
python main.py
```
Type your event description at the prompt. The agent plans, then the evaluator scores.

**Runtime commands (type during conversation):**
| Command | Effect |
| :--- | :--- |
| `exit` / `quit` | End the session |
| `eval off` | Disable evaluator for this session |
| `eval on` | Re-enable evaluator |

### Option C – ADK Web UI
```bash
adk web
```
Navigate to `http://localhost:8000` and select **PlanningPuppet** from the agent dropdown.

---

## Example Input & Output

### Example Input
```text
I'm planning a garden wedding for 80 guests on June 15, 2027 in Bangalore with a total
budget of $24,000. We love a romantic boho aesthetic with pampas grass and dried florals.
Can you build me a complete event plan with venue recommendations?
```

### Example Output (abbreviated)
```markdown
🌸 How wonderful — a garden boho wedding for 80 guests in Bangalore on June 15, 2027!
You have 234 days to plan, and your $24,000 budget is very workable ($300.00/guest).
Here is your complete event plan:

## 💰 Budget Breakdown (Total: $24,000 | 80 guests | $300.00/guest)

| Category                  | %   | Amount      |
|---------------------------|-----|-------------|
| Venue & Catering          | 45% | $10,800.00  |
| Photography & Videography | 12% | $2,880.00   |
| Decor & Florals           | 12% | $2,880.00   |
| Attire & Beauty           | 8%  | $1,920.00   |
| Entertainment & Music     | 8%  | $1,920.00   |
| Contingency Buffer        | 15% | $3,600.00   |

## 📍 Recommended Venues in Bangalore
* **[The Tamarind Tree](https://www.google.com/maps/search/?api=1&query=The+Tamarind+Tree+Avalahalli%2C+Kanakapura+Road%2C+Bangalore)** — ⭐ 4.6 / 5 (2,180 reviews)
  *Vibe:* Heritage courtyards & open lawns, perfect for romantic boho garden weddings.
* **[Templetree Leisure](https://www.google.com/maps/search/?api=1&query=Templetree+Leisure+Green+Glen+Layout%2C+Bellandur%2C+Bangalore)** — ⭐ 4.5 / 5 (1,420 reviews)
  *Vibe:* Balinese-inspired eco-resort with tranquil water bodies and open pavilions.

[🗺️ Explore All Venues on Google Maps](https://www.google.com/maps/search/?api=1&query=outdoor+boho+garden+wedding+venue+in+Bangalore)

## 📅 Planning Timeline
- **Phase 1 (12–9 Months Out):** Lock in venue and photographer.
- **Phase 2 (8–6 Months Out):** Finalise caterer, florist, and entertainment.
- **Phase 3 (5–2 Months Out):** Send invitations, schedule attire fittings.
- **Phase 4 (1 Month to Day-Of):** Confirm final headcount, seating chart, vendor timeline.

## 🎨 Pinterest Inspiration
- [Boho Wedding Decor](https://www.pinterest.com/search/pins/?q=boho+wedding+decor)
- [Pampas Grass Arch](https://www.pinterest.com/search/pins/?q=pampas+grass+arch)
- [Earthy Neutral Table Setting](https://www.pinterest.com/search/pins/?q=earthy+neutral+table+setting)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   🎯  LLM-as-a-Judge Evaluation Report
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Event Type Alignment   ★★★★★  5/5
  Budget Correctness     ★★★★★  5/5
  Timeline Feasibility   ★★★★☆  4/5
  Tone & Empathy         ★★★★★  5/5

  Overall Score: 4.8/5.0
  Verdict: PASS
```

---

## How to Test

```bash
# 1. Run the comprehensive test suite (all 58 unit + live API tests):
python backend_test.py

# 2. Run offline mode only (skips live API calls):
python backend_test.py --offline

# 3. Test the interactive CLI:
python main.py

# 4. Test the Streamlit Web UI:
streamlit run app.py
```

---

## File Structure

```text
agents/planning-puppet/
├── .env.example       # Environment variable template (safe to commit)
├── .gitignore         # Ignores .env, .venv, __pycache__, etc.
├── requirements.txt   # Python dependencies (google-adk, googlemaps, streamlit, etc.)
├── tools.py           # Five discrete ADK function tools (budget, timeline, vendors, inspiration, maps)
├── agent.py           # ADK LlmAgent definition (PlanningPuppet)
├── evaluator.py       # LLM-as-a-Judge quality evaluator
├── main.py            # CLI entry point with Rich terminal UI
├── app.py             # Streamlit interactive web chat UI
├── backend_test.py    # Comprehensive verification suite (unit + live API)
└── README.md          # This file
```

---

## Known Limitations

- **No external live vendor pricing**: While Google Maps Places provides live ratings and locations, budget percentages are based on industry-standard guidelines rather than real-time quote feeds. Final vendor costs vary by season, location, and guest requirements.
- **Session persistence**: Session memory is stored in-memory during the active run (`InMemorySessionService`). For multi-session persistence across server reboots, swap in an SQLite or database-backed ADK session service.
- **Pinterest search URLs**: The agent generates direct Pinterest search links rather than private boards.
- **Tested platforms**: Windows 11, macOS 14, Ubuntu 22.04 with Python 3.10–3.12.

---

## Security & Privacy Considerations

- **Secrets Handling**: All API keys are loaded exclusively from `.env` via `python-dotenv`. The local `.gitignore` strictly blocks `.env` from ever being tracked by Git.
- **Data Privacy**: Only event planning context (guest count, budget, location) is sent to the Gemini API. No PII is collected or stored.
- **No Code Execution**: The agent does not execute arbitrary shell commands or code. All tools are pure, deterministic Python functions.

---

## Future Improvements

- [ ] Export full event plan to a formatted PDF or downloadable checklist.
- [ ] Add persistent session storage (SQLite via ADK session backend).
- [ ] Integrate a real-time vendor booking directory.
- [ ] Multi-currency conversion for international events.
- [x] Build an interactive Streamlit Web UI (`app.py`).
- [x] Integrate Google Maps Places API for venue recommendations.

---

## License

*This project is contributed under the repository's open-source license.*
