# RentRakshak — How to Use (Quick Guide)

This guide helps you run the hackathon demo without last-minute surprises.

**Judges:** start with **[JUDGING_OVERVIEW.md](JUDGING_OVERVIEW.md)** and the long-form **[README.md](README.md)** (full feature descriptions). This file is the command cheat sheet.

## 0. Docker (no Python on your machine)

```bash
cd agents/rentrakshak
docker compose build
docker compose run --rm test    # expect: 40 passed
docker compose run --rm cli     # JSON safety report (suspicious fixture)
docker compose run --rm seed    # demo community DB in Docker volume
```

Full reference: **[DOCKER.md](DOCKER.md)**.

## 1. One-time setup (local Python)

```bash
cd agents/rentrakshak
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env        # optional: add GOOGLE_API_KEY for live ADK chat
python scripts/seed_demo_data.py
```

## 2. Run tests (no API key, no internet)

```bash
pytest -q
```

Expected: **40 passed**.

## 3. Deterministic safety report (recommended for judges)

No LLM — same input always yields the same rule findings.

```bash
python main.py --listing @tests/fixtures/suspicious_listing.txt
python main.py --listing @tests/fixtures/clean_listing.txt
```

## 4. HTML web demo (recommended UI)

```bash
cd agents/rentrakshak
pip install -r requirements.txt
./scripts/run_web_demo.sh
# open http://127.0.0.1:8080
```

Purple dashboard UI → same Python services via REST API. **Analyze Listing** accepts paste, `.txt`, `.pdf` (text extract), and **JPG/PNG/WebP screenshots**.

### Screenshot OCR (Gemma / Gemini vision)

Pick one backend:

```bash
# Local Gemma (you already have Ollama)
ollama pull gemma3:4b
export RENTRAKSHAK_VISION_BACKEND=ollama
export RENTRAKSHAK_OLLAMA_MODEL=gemma3:4b

# Or cloud Gemini
export GOOGLE_API_KEY=your_key
export RENTRAKSHAK_VISION_BACKEND=gemini
```

Upload a NoBroker / WhatsApp screenshot on **Analyze Listing** — text fills the box with a thumbnail preview, then click **Analyse with AI**.

## 4b. Streamlit (legacy / optional)

```bash
streamlit run ui/streamlit_app.py
```

| Tab | What to try |
|-----|-------------|
| Analyze listing | Paste `tests/fixtures/suspicious_listing.txt` content |
| Tenant experiences | Search Koramangala after seed script |
| Vacating / rooms | Search Whitefield for seeded room |
| Karnataka checklist | Scroll sources — not legal advice |

## 5. Local Gemma via Ollama (no Google API key)

You already have `gemma3:1b` and `gemma3:4b` in Ollama. Use **4b** for better tool calling.

```bash
pip install -r requirements-ollama.txt
python scripts/check_ollama.py          # must pass

export RENTRAKSHAK_LLM_BACKEND=ollama
export RENTRAKSHAK_OLLAMA_MODEL=gemma3:4b
# optional smaller/faster: gemma3:1b

adk run adk_agent
# or
adk web adk_agent
```

**Auto mode:** set `RENTRAKSHAK_USE_OLLAMA=true` and leave `GOOGLE_API_KEY` unset — agent picks Ollama.

Deterministic tools (`main.py`, `pytest`) still work without Ollama.

## 6. Google ADK agent with Gemini (needs `GOOGLE_API_KEY`)

From `agents/rentrakshak`:

```bash
export GOOGLE_API_KEY=your_key
adk run adk_agent
# or
adk web adk_agent
```

Example prompts:

- "Analyze this listing and give evidence-backed risks: [paste text]"
- "Estimate rent for 2 BHK semi-furnished in Whitefield using your tool"
- "What should I verify before paying deposit in Karnataka?"

The agent must call tools for rents, risks, and legal references — it should not invent figures.

## 7. Reset demo database

```bash
rm -f data/rentrakshak.db
python scripts/seed_demo_data.py
```

## 8. Optional: Gemma on Vertex (cloud)

Set in `.env` (see `.env.example`). Not required for pytest or Streamlit deterministic flows.

## 9. Optional: Model Armor

Set `MODEL_ARMOR_PROJECT_ID` and `MODEL_ARMOR_TEMPLATE_ID`. If unset, local guardrails still run (see `rentrakshak/guardrails/`).

## 10. Pull request / upstream

Project path: `agents/rentrakshak/` in [gdgcblr/open-source-agents](https://github.com/gdgcblr/open-source-agents).

For manual QA before presenting, follow **FEATURE_VERIFICATION_GUIDE.md** section by section.
