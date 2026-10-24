# Standup Notes

> Turns your messy daily notes into clean standup bullets in one command.

---

## Overview

- **Problem**: Writing the same standup update every morning from scattered notes is boring.
- **Intended Users**: Developers who keep a plain text notes file and hate standup prep.

Prefix each line in your notes with `done:`, `doing:` or `blocked:`. Anything else is skipped.

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

---

## How to Run

```bash
python summarize.py notes.txt
```

A sample `notes.txt` is included so you can try it straight away.

---

## Example Output

```
Standup for notes.txt

Yesterday
  - fixed the login redirect loop
  - reviewed the caching PR
Today
  - writing tests for the CSV export
Blockers
  - waiting on staging database access

1 line skipped (no done/doing/blocked prefix)
```

---

## Known Limitations

- Only understands the three prefixes above, no dates or multiple days yet.
