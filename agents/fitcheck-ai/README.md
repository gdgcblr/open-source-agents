# FitCheck AI — Your Personal Stylist Council

> Upload an outfit (or pick one from your digital wardrobe) and a council of Gemma-powered experts debates the look. You get a scorecard, specific fixes, alternatives from clothes you already own, and a personal colour board that accounts for lighting.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: "Does this look okay?" is a question people ask friends every day, and the answers are vague. Colour-analysis apps are thrown off by bad lighting, and most AI styling tools push you to buy new clothes instead of using what you own.
- **Intended Users**: Anyone getting dressed for an event (work, weddings, talks, dates), people curious about which colours suit them, and builders who want a clear, real-world example of a **multi-agent ADK system running on open-weights Gemma**.

### Key Features
- **Stylist Council (FitCheck)**: four experts judge the look **in parallel**, each on one dimension:
  - **Stylist**: proportions, layering, silhouette
  - **Color Expert**: colour harmony and contrast
  - **Occasion Expert**: whether the look suits the event and dress code (including Indian occasions)
  - **Color Analyst**: how well the look fits *your* palette
- **Colour universe (ShadeMatch)**: an optional selfie plus the colours you love produce a personal palette (skin undertone, depth, contrast, closest season), hero colours, and colours to keep away from your face.
- **Lighting-aware colour science**: white balance (estimated from the background, so it doesn't cancel out your skin's warmth), exposure correction only when a photo is actually mis-exposed, and a **confidence score** that tells the agents to hedge on bad photos.
- **Shopping Skeptic**: picks alternative outfits **only from your wardrobe**. Candidates are pre-generated in code, so the model cannot invent clothes you don't own.
- **Head Stylist**: settles disagreements and outputs a structured JSON scorecard.
- **Live debate UI**: watch each agent's verdict stream in. You can speak the occasion into the mic, and the browser can read the verdict aloud.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+ (required by ADK), vanilla HTML/CSS/JS frontend
- **Agent Framework**: Google Agent Development Kit (ADK): `SequentialAgent`, `ParallelAgent`, `LlmAgent`, a custom `BaseAgent`, session-state templating
- **Models**: **Gemma 3 4B** (vision) running locally through **Ollama**, connected via ADK's `LiteLlm` wrapper. Any LiteLLM model string can be swapped in.
- **Other libraries**: FastAPI + Uvicorn (streaming server), Pillow + NumPy (colour engine). No external paid APIs.

---

## Architecture & Data Flow

```
Browser ──POST /api/fitcheck──▶ FastAPI ──▶ ADK Runner (session state = your inputs)
                                              │
  SequentialAgent "FitCheckCouncil"           ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ 1. ColorLab (custom BaseAgent, pure Python, no LLM)                      │
  │    selfie/outfit photo → white balance + exposure fix → skin undertone,  │
  │    dominant colours, harmony scheme, personal palette, wardrobe combos   │
  │                                   │ writes facts to session state        │
  │ 2. OutfitReader (Gemma vision) → objective garment description           │
  │                                   │                                      │
  │ 3. ParallelAgent "StylistCouncil"                                        │
  │      Stylist │ ColorExpert │ OccasionExpert │ ColorAnalyst  (each: SCORE)│
  │                                   │                                      │
  │ 4. ShoppingSkeptic → picks 3 combos from your wardrobe (by ID only)      │
  │ 5. HeadStylist → resolves the debate → JSON scorecard                    │
  └──────────────────────────────────────────────────────────────────────────┘
                                              │
Browser ◀── NDJSON stream (each agent's take, then the final result) ─┘
```

**Design principle: measure in code, reason with Gemma.** Small models are unreliable at reading exact colours off pixels, so all colour facts are computed deterministically in `color_engine.py` and passed into prompts through ADK state templating (`{palette_text}`, `{harmony_text}`, …). Gemma handles what it's good at: judgement, taste and explanation. This also means every step works with Gemma builds that **don't support tool-calling**.

---

## Prerequisites

- Python **3.11+** (if your system Python is older, `uv` can install a newer one, as shown below)
- [Ollama](https://ollama.com) installed and running
- ~4 GB free RAM/VRAM for `gemma3:4b` (use `gemma3:12b` for better judgement if your machine can handle it)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/fitcheck-ai
   ```

2. **Pull the Gemma model:**
   ```bash
   ollama pull gemma3:4b
   ```

3. **Create a virtual environment and install dependencies:**
   ```bash
   # with uv (recommended — fetches Python 3.12 if needed)
   uv venv --python 3.12 && source .venv/bin/activate
   uv pip install -r requirements.txt

   # or with plain venv (Python 3.11+)
   python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. **Configure environment variables (optional; the defaults work with local Ollama):**
   ```bash
   cp .env.example .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `FITCHECK_MODEL` | No | `ollama_chat/gemma3:4b` | LiteLLM model string used by all agents |
| `FITCHECK_VISION_MODEL` | No | same as `FITCHECK_MODEL` | Model used by the OutfitReader (must accept images) |
| `OLLAMA_API_BASE` | No | `http://localhost:11434` | Ollama endpoint |
| `GEMINI_API_KEY` | Only for hosted Gemma | *None* | If you set `FITCHECK_MODEL=gemini/gemma-3-27b-it` (untested) |
| `HOST` / `PORT` | No | `127.0.0.1` / `8000` | Web server address |

---

## How to Run

```bash
ollama serve            # if Ollama isn't already running
python server.py        # or: uvicorn server:app --reload --port 8000
```
Open **http://127.0.0.1:8000** and:
1. Upload an outfit photo, **or** switch to *Pick from wardrobe* and select 2+ pieces.
2. (Optional) add a selfie and tap the colours you love. A colour board preview appears instantly, with no LLM involved.
3. Type or speak the occasion, then press **Convene the council**.

The wardrobe lives in `fitcheck_ai/data/wardrobe.json`. Edit it to make it your own closet.

---

## Example Input & Output

### Example Input
Wardrobe mode: *Sage silk blouse + Beige wide-leg pants + Tan block heels + Camel trench coat*. Favourite colours: sage, fuchsia. Occasion: *"Speaking at a tech conference"*.

### Example Output (deterministic Color Lab step; a real run)
```
Palette (harmony rules built around the colours you love):
  sage #9caf88, lilac #9b8ea9, fuchsia #c42f87, coral #cb5b65, emerald #45ae70, ivory #f4efe1, navy #1f2a44
Outfit harmony: neutrals + one accent, value contrast: low, rule-based harmony 8.5/10
Wardrobe alternatives handed to the Shopping Skeptic:
  C1: Sage silk blouse + Indigo straight jeans + Black loafers + Burgundy crossbody bag | fit 8.9/10
  C2: Fuchsia kurta top + Beige wide-leg pants + Tan block heels + Burgundy crossbody bag | fit 8.9/10
  C3: Rust ribbed knit + Black tailored trousers + Black loafers + Black leather jacket + Burgundy crossbody bag | fit 8.4/10
```
The final scorecard has this shape (values vary by model and run):
```json
{
  "verdict": "...", "overall_score": 7.4,
  "scores": {"silhouette": 7, "color": 8, "occasion": 7, "palette_fit": 8},
  "debate": [{"topic": "...", "resolution": "..."}],
  "improvements": ["...", "...", "..."],
  "alternatives": [{"combo_id": "C1", "why": "..."}],
  "color_board": {"hero_colors": ["..."], "avoid_near_face": ["..."], "tip": "..."},
  "buy_next": "nothing — shop your closet"
}
```
*(Contributors: paste a real Gemma scorecard from your own machine here before opening the PR.)*

---

## How to Test

```bash
pytest -q
```
The tests run **fully offline**. A fake Gemma model is plugged into every `LlmAgent`, so they check:
- that white balance removes a warm cast and that skin detection works on selfies,
- harmony classification, and that wardrobe combos only use owned items,
- the **whole ADK pipeline end-to-end** through the FastAPI endpoint: all 8 agents speak, state templating injects the measured facts into prompts, the JSON scorecard parses, and a made-up combo ID from the model is dropped.

Manual check: start the server, choose *Pick from wardrobe*, select 3 items, and press the button. You should see the Color Lab, Outfit Reader and the four council members stream in, followed by a scorecard.

---

## Known Limitations

- **Colour analysis is an estimate**, not a professional draping session. Strong coloured lighting can still flip a borderline undertone. When that happens, confidence drops (shown in the UI) and the Color Analyst is told to call the reading tentative.
- Skin detection uses a YCrCb heuristic and doesn't detect faces. Very busy backgrounds in skin-like colours (wood, sand) can reduce accuracy.
- Outfit-photo colours are taken from the centre of the frame, so heavy background clutter can leak in.
- `gemma3:4b` sometimes returns imperfect JSON. The server repairs common issues and otherwise rebuilds the scorecard from each expert's `SCORE:` line (marked in the UI).
- The wardrobe is a local JSON file, with no image upload per garment yet.
- A full run makes 7 model calls. On a laptop CPU this can take 30–90 s; a GPU or Apple Silicon is much faster.
- ADK 2.x marks `SequentialAgent`/`ParallelAgent` as deprecated in favour of the new `Workflow` API. They still work, and migrating is listed under Future Improvements.
- Tested on Linux with Python 3.13. macOS and Windows are expected to work but haven't been verified.

---

## Security & Privacy Considerations

- **Secrets Handling**: no keys are needed for the default local setup. Optional keys are read from `.env`, which is git-ignored.
- **Data Privacy**: with Ollama, **photos never leave your machine**: images are processed in memory and nothing is written to disk. If you switch to a hosted model, photos are sent to that provider.
- **Safety**: the agents don't run shell commands or arbitrary code and have no tools beyond reading session state. Prompts ask for kind, specific feedback about outfits, never about bodies.

---

## Future Improvements

- [ ] Migrate the pipeline to ADK's `Workflow` API
- [ ] Real "debate" round 2: each expert sees the others' takes and can rebut
- [ ] Photo-based wardrobe upload (Gemma tags each garment's category and colour)
- [ ] LoRA-fine-tune Gemma on stylist feedback for sharper critiques
- [ ] Face landmarking for more precise skin, eye and hair sampling
- [ ] Full voice mode (conversational follow-ups)

---

## License

*This project is contributed under the repository's open-source license.*
