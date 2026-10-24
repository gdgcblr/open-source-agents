# FitCheck AI

> A council of Gemma agents reviews your outfit, scores it, suggests fixes and alternatives from your own wardrobe, and builds your personal colour palette.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: "Does this look okay?" usually gets a vague answer. Colour-analysis apps are thrown off by bad lighting, and most styling tools push you to buy something new instead of using what you own.
- **Intended Users**: Anyone getting dressed for an event (work, interviews, weddings, talks), and developers looking for a clear example of a multi-agent ADK app running on Gemma.

### Key Features
- **Stylist council**: four agents judge the outfit in parallel: silhouette, colour harmony, fit for the occasion, and fit with your palette.
- **Colour palette from a selfie**: white balance and exposure are corrected before measuring skin undertone, depth and contrast. A confidence score drops for poor photos.
- **Wardrobe-first suggestions**: alternative outfits are built only from clothes in `wardrobe.json`, so the model can't invent items you don't own.
- **Scorecard**: a head stylist settles the experts' disagreements and returns a structured score, fixes and a colour board.
- **Live debate**: each agent's verdict streams into the page as soon as it's ready.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+, plain HTML/CSS/JS frontend
- **Agent Framework**: Google ADK (`SequentialAgent`, `ParallelAgent`, `LlmAgent`, a custom `BaseAgent`)
- **Models**: Gemma 4 (`gemma-4-26b-a4b-it`) through the Gemini API
- **Other**: FastAPI, Uvicorn, Pillow, NumPy

---

## Architecture & Data Flow

```
Browser ── POST /api/fitcheck ──▶ FastAPI ──▶ ADK Runner
                                                │
  ColorLab         Python only: lighting correction, skin tone, palette,
                   outfit harmony, outfit combos from the wardrobe
  OutfitReader     Gemma describes the outfit (reads the photo if there is one)
  StylistCouncil   Stylist │ Colour expert │ Occasion expert │ Colour analyst  (parallel)
  ShoppingSkeptic  picks the best combos from the user's own wardrobe
  HeadStylist      resolves the debate, returns a JSON scorecard
                                                │
Browser ◀── streamed JSON lines: one per agent, then the final result
```

Colours are measured in code (`colors.py`) and passed to the agents through ADK session state, because small models are unreliable at reading exact colours from pixels.

| File | What it does |
| :--- | :--- |
| `main.py` | FastAPI app, streaming endpoint, scorecard parsing |
| `council.py` | ADK agents and pipeline |
| `prompts.py` | Agent instructions |
| `colors.py` | Lighting correction, skin analysis, palettes, colour harmony |
| `wardrobe.py` / `wardrobe.json` | Wardrobe data and outfit combinations |
| `static/index.html` | The web page |

---

## Prerequisites

- Python 3.11 or newer
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) (the free tier works)

---

## Installation & Setup

```bash
cd agents/fitcheck-ai
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then add your GOOGLE_API_KEY
```

> On macOS, if the project is inside an iCloud-synced folder (like `~/Documents`), create the virtualenv somewhere else, for example `python3 -m venv ~/.venvs/fitcheck-ai`. iCloud can time out reading the thousands of files in a virtualenv.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | Yes | *None* | Gemini API key |
| `FITCHECK_MODEL` | No | `gemma-4-26b-a4b-it` | Use `gemma-4-31b-it` for stronger but slower answers |

---

## How to Run

```bash
uvicorn main:app --reload
```

Open http://127.0.0.1:8000, pick a few pieces from the wardrobe (or upload a photo), choose an occasion and press **Convene the council**. A run takes about 20–30 seconds.

To use your own clothes, edit `wardrobe.json`.

---

## Example Input & Output

### Example Input
Wardrobe: sage silk blouse, beige wide-leg pants, tan block heels, camel trench coat. Favourite colours: sage, fuchsia. Occasion: "Speaking at a tech conference".

### Example Output (real run, `gemma-4-26b-a4b-it`, debate section left out)
```json
{
  "verdict": "A sophisticated, tonal ensemble that requires structural discipline and higher contrast to truly command a keynote stage.",
  "scores": {"silhouette": 7, "color": 8.5, "occasion": 9, "palette_fit": 7},
  "overall_score": 8.1,
  "improvements": [
    "Tuck the silk blouse into the pants to establish a clear waistline.",
    "Swap beige pants for ivory to increase contrast and make the sage blouse pop.",
    "Wear the trench coat open or belted to create slimming vertical lines.",
    "Add structured accessories like a leather watch and minimalist gold jewelry."
  ],
  "alternatives": [
    {"combo_id": "C2", "why": "Uses high-impact fuchsia near the face to command immediate keynote attention."},
    {"combo_id": "C1", "why": "Provides an organic sage pop against a darker indigo base for professional depth."}
  ],
  "color_board": {
    "hero_colors": ["Sage", "Fuchsia", "Emerald", "Navy"],
    "avoid_near_face": ["Ivory", "Coral"],
    "tip": "Use high-impact jewel tones near the face to maintain your natural glow and command attention."
  },
  "buy_next": "nothing — shop your closet"
}
```

---

## How to Test

```bash
pytest -q
```

The tests run offline. A fake Gemini client sits behind ADK's real model class, so they check the full pipeline without an API key: all eight agents run, the photo reaches the outfit reader, thinking text is hidden, the scorecard parses, made-up outfit IDs are dropped, and an empty model reply doesn't break the run.

---

## Known Limitations

- Colour analysis is an estimate. Strong coloured lighting can still shift a borderline undertone; the confidence score drops when that happens.
- Skin detection uses colour thresholds, not face detection, so skin-coloured backgrounds (wood, sand) can reduce accuracy.
- Each run makes 7 model calls. Several quick runs in a row can hit free-tier rate limits; requests are retried with backoff.
- The wardrobe is a JSON file; there's no photo upload for individual garments yet.
- Tested on macOS and Linux.

---

## Security & Privacy Considerations

- **Secrets Handling**: the API key is read from `.env` (git-ignored) on the server and never sent to the browser.
- **Data Privacy**: outfit photos and selfies are sent to the Gemini API for processing. Nothing is stored on disk.
- **Safety**: the agents have no tools and don't run code. Prompts ask for feedback on clothes, not bodies.

---

## Future Improvements

- [ ] Second debate round where experts respond to each other
- [ ] Add garments to the wardrobe by photo
- [ ] Fine-tune Gemma on stylist feedback
- [ ] Face landmarks for more precise skin, eye and hair sampling

---

## License

This project is contributed under the repository's open-source license.
