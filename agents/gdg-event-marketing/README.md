# GDG Event Marketing Agent

> Turn a published GDG Community event into review-ready LinkedIn, X, and email
> newsletter drafts with Gemini—or explore the interface with offline sample data.

---

## Overview

### Problem Statement & Intended Users

GDG organizers often need to rewrite the same event details for several
communication channels. This tool fetches the nearest upcoming published event
from GDG Community (Bevy) and drafts channel-specific copy for organizers to
review and edit.

**Intended users:** GDG chapter organizers and community volunteers.

### Key Features

- Fetches the nearest future published event for a chapter ID.
- Lists upcoming events so organizers can choose the right event.
- Lets organizers edit event facts before generating, or use a fully custom event.
- Generates LinkedIn, X, and email newsletter drafts with Gemini.
- Adds audience, tone, call-to-action, extra guidance, and channel-selection controls.
- Provides editable drafts, per-channel regeneration, word/character counts,
  copy-to-clipboard, and Markdown/text export.
- Keeps network work off the UI thread and presents actionable validation/errors.
- Includes offline demo mode with fictional event data; no credentials or network
  are needed to explore the interface.
- Never publishes content to social media or writes drafts to files.

### UI Preview

![GDG Event Marketing desktop UI showing fictional demo drafts](screenshots/ui-demo.png)

The screenshot is from offline demo mode. The chapter, speaker, event, and link
shown are fictional; demo output is not live API-generated content.

---

## Technical Stack

- **Language & Runtime:** Python 3.9+ (Python 3.10+ recommended)
- **Agent framework / core library:** Python script with Google Gen AI SDK
- **Model:** `gemini-3.8-flash` by default; override with `GEMINI_MODEL`
- **Desktop UI:** Tkinter (included with most standard Python distributions)
- **External APIs:** Public GDG Community event API and Gemini API
- **Other dependencies:** Requests and python-dotenv

---

## Architecture & Data Flow

Live mode reads local configuration, requests published events for the selected
chapter, filters out past events, and sends the nearest upcoming event details
to Gemini for three separate drafts. The UI runs the request away from the main
window thread, presents each draft in a tab, and supports copying a selected
draft. It does not publish or persist generated content.

```text
Local chapter ID ──> GDG Community event API ──> nearest upcoming event
                                                  │
Local Gemini key ─────────────────────────────────┴─> Gemini ──> 3 drafts
                                                                    │
                                                    UI tabs / terminal output
```

Offline demo mode bypasses both APIs and displays clearly labeled fictional
sample content.

---

## Prerequisites

- Python 3.9 or newer; Python 3.10+ is recommended (Python 3.9 is end-of-life).
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)
  for live generation only.
- Internet access to gdg.community.dev and the Gemini API for live generation.

---

## Installation & Setup

From the repository root, enter the project:

```powershell
cd agents\gdg-event-marketing
```

On macOS or Linux:

```bash
cd agents/gdg-event-marketing
```

Create and activate a virtual environment, then install dependencies.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, invoke `.venv\Scripts\python.exe` directly.
On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

---

## Configuration & Environment Variables

For live mode, copy `.env.example` to `.env` and fill in your own values.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
notepad .env
```

macOS or Linux:

```bash
cp .env.example .env
```

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Live mode | None | Your private Gemini API key. |
| `GDG_CHAPTER_ID` | Live mode | None | Chapter ID from the GDG Community page. |
| `GEMINI_MODEL` | No | `gemini-3.8-flash` | Gemini model available to your account. |

Find the chapter ID on your chapter page at
[gdg.community.dev](https://gdg.community.dev/). If it is not displayed, view
the page source and search for `Globals.chapter_id`; the URL slug is not
necessarily the numeric chapter ID. You can also enter the ID in the UI or pass
it to the CLI with `--chapter-id`.

**Keep `.env` local.** It is ignored by Git. Do not add personal chapter
settings, API keys, or other credentials to source files or pull requests.
Values typed into the UI are only held in memory for that run; the UI never
saves them. The UI masks the API-key field while typing.

---

## How to Run

### Desktop UI

Launch the regular interface:

```powershell
python ui.py
```

For a presentation-ready window with the sample drafts loaded:

```powershell
python ui.py --demo
```

Choose **Offline demo** to explore without a key or network. Choose **Live**,
enter a chapter ID and Gemini key (or configure them in `.env`), then click
**Find events** to choose from upcoming chapter events, or select **Live:
custom event** to enter one manually. Edit the fetched event details, select
channels, set a tone, audience, and call to action, then click **Generate
drafts**. Edit drafts in-place, regenerate a selected channel, copy it, or save
all drafts as Markdown/text. Review generated copy before using it; the app
never posts content.

### Offline CLI demo

```powershell
python agent.py --demo
```

The demo chapter `DEMO-CHAPTER-001`, its event, speaker, and example link are
fictional. Do not present demo output as live API-generated content or use its
fictional link.

### Live CLI mode

```powershell
python agent.py
```

Or specify a chapter for one run:

```powershell
python agent.py --chapter-id 12345
```

The agent fetches the nearest upcoming published event, then prints the
LinkedIn, X, and newsletter drafts. Past events are skipped. If no upcoming
event exists, it reports that without calling Gemini.

---

## Example Input & Output

### Example input (fictional offline demo)

```text
Chapter: DEMO-CHAPTER-001 (fictional)
Event: Building AI for Science: Community Workshop
Location: Online
```

### Example output (fictional sample)

```text
LinkedIn:
Curious about AI for research? Join us for Building AI for Science:
Community Workshop!

A fictional hands-on introduction to using machine learning for research
workflows. Bring a laptop and your curiosity.
...

X:
Explore AI for research at Building AI for Science: Community Workshop! ...
```

The offline demo renders sample content deterministically. Live Gemini output
will vary and must be fact-checked before publication.

---

## How to Test

Run the offline unit tests from this folder:

```powershell
python -m unittest discover -s tests
```

Check syntax:

```powershell
python -m py_compile agent.py ui.py prompts.py tests\test_agent.py
```

Run `python ui.py --demo` to manually verify the desktop interface, tabs, and
copy button without using network access or credentials.

---

## Known Limitations

- Live mode requires a valid Gemini key and a chapter with an upcoming
  published event.
- Event details depend on the public GDG Community API response.
- Drafts may need editing for local voice, timing, accessibility, and platform
  conventions; generated copy is not automatically fact-checked.
- This project creates drafts only; it does not connect to LinkedIn, X, or email
  services to publish or send content.
- Tkinter must be present in the Python distribution to launch the desktop UI.

---

## Security & Privacy Considerations

- **Secrets handling:** The local `.env` is ignored by Git. The example file
  contains placeholders only. UI-entered API keys are masked and are not saved.
- **Data privacy:** In live mode, public event details are sent to Gemini to
  generate drafts. Do not include private attendee information in event data.
  Offline demo mode makes no network requests.
- **Safety:** The agent does not execute model-generated code, access LinkedIn
  credentials, or publish content. A human should review all drafts.

---

## Future Improvements

- [ ] Add localization and chapter-specific brand voice profiles.
- [ ] Add more social channels and configurable platform limits.
- [ ] Add scheduled campaign calendars and opt-in reminders.

---

## License

This project is contributed under the repository's open-source license.
