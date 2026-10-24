# Gemini Haiku

> Give it a topic, get back a haiku written by Gemini.

---

## Overview

- **Problem**: A quick, friendly demo of calling the Gemini API with nothing but the standard library.
- **Intended Users**: Developers trying the Gemini API for the first time.

---

## Prerequisites

- Python 3.10+
- A Gemini API key (free from [Google AI Studio](https://aistudio.google.com/apikey))

---

## Installation & Setup

1. **Create a virtual environment and install dependencies:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

2. **Configure your API key:**
   ```bash
   cp .env.example .env
   ```
   Open `.env` and replace the placeholder with your own key.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes | *None* | Your Gemini API key |
| `GEMINI_MODEL` | No | `gemini-flash-latest` | Model used to write the haiku |

---

## How to Run

```bash
python haiku.py "monsoon evenings in Bengaluru"
```

---

## Example Output

The haiku is written by Gemini, so the three lines change on every run:

```
Topic: monsoon evenings in Bengaluru
<three lines written by Gemini>
```

If the key is missing, the script stops with an error naming `GEMINI_API_KEY` instead of printing anything.

---

## Known Limitations

- Needs network access and a valid key, there is no offline mode.
