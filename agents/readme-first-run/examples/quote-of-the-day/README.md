# Quote of the Day

> A tiny command line tool that prints a programming quote for any day of the year.

---

## Overview

- **Problem**: Our team channel wanted a daily quote and nobody wanted to pick one by hand.
- **Intended Users**: Anyone who wants a quote in their terminal, a cron job or a chat bot.

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

2. **Configure (optional):**
   ```bash
   cp .env.example .env
   ```
   Set `QUOTE_CATEGORY` in `.env` to `engineering` or `open-source`.

---

## How to Run

```bash
python main.py --day 3
```

Leave out `--day` to use today's day of the year.

---

## Example Output

```
Quote of the day #3 (engineering)
"Make it work, make it right, make it fast."
  - Kent Beck
```

---

## Known Limitations

- Quotes live in `quotes.json`, there is no command to add new ones yet.
