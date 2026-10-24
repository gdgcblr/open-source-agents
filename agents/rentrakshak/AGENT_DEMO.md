# RentRakshak — agentic demo (ADK)

Use this when you need to show **the Google ADK agent**: the LLM **chooses tools** from natural language.  
The HTML app at `:8080` calls the same Python logic **without** the agent loop.

## Before you present (2 terminals)

**Terminal A — optional product UI**

```bash
cd agents/rentrakshak && source .venv/bin/activate
./scripts/run_web_demo.sh
# http://127.0.0.1:8080
```

**Terminal B — agent (this is the agentic demo)**

```bash
cd agents/rentrakshak && source .venv/bin/activate
chmod +x scripts/run_adk_demo.sh
./scripts/run_adk_demo.sh
```

Open **http://127.0.0.1:8000/dev-ui/**  
Select agent **`rentrakshak`** if prompted.

### Gemini instead of Ollama

```bash
export GOOGLE_API_KEY=your_key
export RENTRAKSHAK_LLM_BACKEND=gemini
./scripts/run_adk_demo.sh
```

---

## What to say in 20 seconds

> “The website buttons call our safety engine directly.  
> Here is the **Google ADK agent**: I ask in plain English, and **Gemini/Gemma decides which of 13 tools to call** — rent estimate, red flags, community search — instead of us hard-coding the flow.”

---

## Demo script (copy-paste prompts)

### 1. Full safety report (star demo)

Paste this as **one user message** (expand the listing block):

```
I'm about to pay a ₹50,000 token for this Koramangala listing. Use your tools and give me a safety report with red flags and rent context.

LISTING:
2 BHK in Koramangala near forum mall. Rent Rs 15000 only!!!
URGENT pay token today before viewing — transfer to my friend account.
Send OTP for booking confirmation.

CHAT:
Owner said rent is 15000 but after OTP verification price becomes 28000.
```

**Show judges:** In ADK UI, **tool calls** such as `generate_rental_safety_report_tool` or `detect_rental_red_flags` + `estimate_bengaluru_rent_tool`.  
**Say:** “Rule IDs and excerpts come from **deterministic tools**, not the model making up scams.”

---

### 2. Rent only (single tool)

```
What is a fair monthly rent range for a semi-furnished 2 BHK in Koramangala? Use the rent tool and include limitations.
```

Expect: `estimate_bengaluru_rent_tool` with min/median/max from JSON.

---

### 3. Community (agent + SQLite)

First seed data once (any terminal):

```bash
cd agents/rentrakshak && source .venv/bin/activate
python scripts/seed_demo_data.py
```

Then in ADK chat:

```
Search anonymous tenant experiences in HSR Layout about deposits or unexpected charges. Summarize patterns only — do not claim anyone is guilty.
```

Expect: `search_anonymous_experiences_tool`.

---

### 4. Checklist + law (no invented deposit cap)

```
What should I verify before signing a rental agreement in Karnataka? Use checklist and legal guidance tools.
```

Expect: `build_rental_checklist_tool`, `get_karnataka_rental_guidance_tool`.

---

### 5. Vacating board

```
Show active vacating or room posts in Whitefield under ₹35,000 per month.
```

Expect: `search_available_rooms_tool`.

---

## Side-by-side with :8080 (strong closer)

1. On **8080** → Analyze → **Scam sample** → instant JSON-style report (no LLM).  
2. On **8000** → same listing in natural language → agent **routes** to the same backend via tools.  
3. **Say:** “Same trust layer; ADK adds **conversational orchestration** for GDG Cloud.”

---

## Troubleshooting

| Problem | Fix |
|--------|-----|
| Ollama errors | `ollama serve`, `ollama pull gemma3:4b` |
| `No module named 'mcp'` | `pip install -r requirements-ollama.txt` (includes `mcp` for LiteLLM) |
| Tool loop (checklist spam) | **New session** after code update; prefer `generate_rental_safety_report_tool` prompt; callbacks block duplicate tools |
| Slow first reply | Gemma 4b on CPU — wait ~30–60s; or use Gemini |
| Empty community | `python scripts/seed_demo_data.py` |
| Port busy | `RENTRAKSHAK_ADK_PORT=8001 ./scripts/run_adk_demo.sh` |

---

## Code pointers (if asked)

| Piece | Path |
|-------|------|
| ADK `Agent` + instructions | `rentrakshak/agent.py` |
| 13 tools | `rentrakshak/tools/registry.py` |
| ADK entry | `adk_agent/agent.py` |
| Model (Gemini / Ollama) | `rentrakshak/llm.py` |
