# Namma Civic Agent

> Snap a photo of a civic problem in Bengaluru and get a ready-to-send complaint, in English and Kannada, addressed to the right authority.

> ⚠️ **Data status: testing only.** For testing and demos, every entry in `namma_civic_agent/data/*.json` is marked `"verified": true`, so replies show contacts without an "unverified" label. **These entries have not been checked against official sources.** Before any production use, verify each authority, department mapping, helpline and escalation step against official sources, fill in `source` for each entry, add missing channels (portal URLs, social handles, traffic police contacts), and add more issue types or details if required. Set `"verified": false` on anything you cannot confirm; the agent will then label it as unverified.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Potholes, garbage black-spots, broken streetlights, sewage overflows and open manholes often go unreported. Residents don't know which authority handles what (city corporation, BESCOM, BWSSB or traffic police), where to file, or how to write a complaint that gets acted on. Many also assume, wrongly, that streetlights belong to BESCOM or that every drain belongs to BWSSB.
- **Intended Users**: Bengaluru residents, resident welfare associations (RWAs) and civic volunteers.

### Key Features
- **Photo understanding**: Classifies a photo (or text description) into one of 17 civic issue categories using a multimodal model.
- **Grounded routing**: The authority, department, helplines and escalation path come from curated local JSON data, not from the model's memory, and the agent is instructed never to invent contact details.
- **Bilingual drafts**: Writes a structured complaint in English and natural Kannada.
- **Safety first**: Critical hazards (live wires, open manholes) get keep-away advice and the emergency number before anything else.
- **Guardrails in code, not just the prompt**: Every model reply passes through an output filter that removes any phone number, URL, email or social handle that isn't in the curated data or in the user's own message.
- **Boundaries in the prompt**: Stays on civic issues only, sticks to facts the user gave or the photo shows (no embellishment), never invents ward numbers, officer names or timelines, treats text inside photos as data rather than instructions, and refuses false or harassing complaints.
- **Honest about data**: Any contact marked `"verified": false` in the data is labelled as unverified in every reply.
- **Drafts, never files**: The user stays in control of submission.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+
- **Agent Framework**: [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) 2.x
- **Models**: Gemini 3.5 Flash (default, configurable via `MODEL_NAME`). Other Gemini models with image input should also work, but are untested.
- **External APIs / Tools**: Gemini API only. Routing data is local JSON.
- **Usage per complaint**: about 4 model requests, ~11k input and ~1k output tokens (measured with `smoke_test.py`). Works on the Gemini free tier (subject to its rate limits); no paid API is required.

---

## Architecture & Data Flow

```
[Photo + location] --> [ADK Runner] --> [Gemini: see, classify, reason, write]
                                              |
                       +----------------------+----------------------+
                       |                      |                      |
              list_issue_types()     find_department()     get_filing_channels()
                       |                      |                      |
                       +-------- data/issue_types.json, data/authorities.json
                                              |
                                              |
                     block_unverified_contacts() (after_model_callback)
                                              |
[Issue + authority + severity + EN/KN draft + where to file + escalation]
                                              |
                                  save_complaint() (optional, local .md)
```

```
namma-civic-agent/
├── namma_civic_agent/
│   ├── __init__.py
│   ├── agent.py              # ADK agent definition (model, instruction, tools)
│   ├── prompt.py             # System instruction: workflow, safety rules, reply format
│   ├── tools.py              # Python functions the model can call
│   ├── guardrails.py         # Output filter: strips contact details not in the data
│   └── data/
│       ├── issue_types.json  # 17 issue categories -> authority + department
│       └── authorities.json  # Authorities -> helplines, portals, escalation path
├── tests/                    # Offline tests for tools and guardrails (no API key needed)
├── smoke_test.py             # One-shot live run: prints tool calls + token usage
├── examples/                 # Sample photos and transcripts from real runs
├── requirements.txt
└── .env.example
```

**Design choice:** the model handles what it is good at (seeing the photo, understanding messy input, reasoning about severity, writing well in two languages). Facts that must be correct, such as who handles what and how to reach them, live in the JSON files and reach the model only through tools.

---

## Prerequisites

- Python 3.11 or newer (required by `google-adk`)
- pip
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) (a free tier is available)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/namma-civic-agent
   ```

2. **Create a virtual environment and install dependencies:**
   ```bash
   python3 --version          # must print 3.11 or newer; otherwise use e.g. python3.12
   python3 -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # then edit .env and set GOOGLE_API_KEY
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | Yes | *None* | Gemini API key from Google AI Studio |
| `GOOGLE_GENAI_USE_ENTERPRISE` | Yes | `0` | Keep `0` to use an AI Studio API key instead of Vertex AI |
| `MODEL_NAME` | No | `gemini-3.5-flash` | Gemini model to use (must accept images) |
| `COMPLAINTS_DIR` | No | `./complaints` | Where `save_complaint` writes Markdown drafts |

---

## How to Run

From `agents/namma-civic-agent/`, with the virtual environment active:

```bash
# Browser chat UI (supports photo upload). Open http://localhost:8000
adk web

# Or chat in the terminal (text only)
adk run namma_civic_agent
```

In the web UI, select `namma_civic_agent`, attach a photo, and describe where it is.

```bash
# Or run a single request non-interactively (prints tool calls and token usage)
python smoke_test.py "Garbage dumped near Indiranagar metro station for 5 days"
python smoke_test.py --image examples/<your-photo>.jpg "Near 100 Feet Road, Indiranagar"
```

---

## Example Input & Output

Genuine run on 2026-10-24 with `gemini-3.5-flash`, using a text description (`python smoke_test.py "..."`). Output is unedited apart from trailing whitespace. (This run was recorded while the data was still marked `"verified": false`, which is why 1533 carries the "unverified" label.)


### Example Input
```
There's a big pothole on 80 Feet Road, Koramangala 4th Block, near the Sony World signal.
Bikes are swerving around it. It's been there about 2 weeks.
```

### Example Output
```
[tool call] list_issue_types({})
[tool call] find_department({'issue_type': 'pothole'})
[tool call] get_filing_channels({'authority_id': 'city_corporation'})
**Issue:** Pothole / damaged road surface (ರಸ್ತೆ ಗುಂಡಿ)
**Responsible:** Bengaluru city corporation (Greater Bengaluru Authority, formerly BBMP), Roads / Engineering
**Location:** 80 Feet Road, Koramangala 4th Block, near Sony World signal
**Severity:** High – Located on a high-density arterial corridor, causing two-wheelers to swerve suddenly into oncoming traffic, creating a major risk of severe accidents.

---

**Draft complaint (English)**

**Subject:** Urgent repair required for dangerous pothole on 80 Feet Road, Koramangala 4th Block

To the Executive Engineer / Road Infrastructure Department,
Bengaluru City Corporation,

I am writing to draw your urgent attention to a severe, deep pothole on 80 Feet Road, Koramangala 4th Block, near the Sony World signal junction. This road defect has remained neglected for approximately two weeks and continues to worsen.

Because of its depth and location on a high-volume road, two-wheelers and drivers are frequently forced to swerve into neighboring lanes to avoid it. This poses a grave hazard of collisions, especially during peak hours and after dusk.

I request you to conduct an immediate inspection and resurface/patch this section of the road without delay to safeguard commuters.

Thank you.

Sincerely,
[Your name]
[Your phone number]

---

**Draft complaint (ಕನ್ನಡ)**

**ವಿಷಯ:** ಕೋರಮಂಗಲ 4 ನೇ ಬ್ಲಾಕ್‌ನ 80 ಫೀಟ್ ರಸ್ತೆಯಲ್ಲಿರುವ ಅಪಾಯಕಾರಿ ರಸ್ತೆ ಗುಂಡಿ ತಕ್ಷಣ ದುರಸ್ತಿ ಮಾಡುವಂತೆ ಮನವಿ

ಗೌರವಾನ್ವಿತ ಅಧಿಕಾರಿಗೆ,
ಬೆಂಗಳೂರು ನಗರ ಪಾಲಿಕೆ (ರಸ್ತೆ ಮತ್ತು ಎಂಜಿನಿಯರಿಂಗ್ ವಿಭಾಗ),

ಕೋರಮಂಗಲ 4 ನೇ ಬ್ಲಾಕ್‌ನ 80 ಫೀಟ್ ರಸ್ತೆಯಲ್ಲಿ, ಸೋನಿ ವರ್ಲ್ಡ್ ಸಿಗ್ನಲ್ ಸಮೀಪ ಇರುವ ದೊಡ್ಡ ರಸ್ತೆ ಗುಂಡಿಯ ಕುರಿತು ನಿಮ್ಮ ಗಮನಕ್ಕೆ ತರಬಯಸುತ್ತೇನೆ. ಈ ಗುಂಡಿ ಕಳೆದ ಸುಮಾರು ಎರಡು ವಾರಗಳಿಂದ ಹಾಗೆಯೇ ಇದ್ದು, ರಸ್ತೆ ಮತ್ತಷ್ಟು ಹಾಳಾಗುತ್ತಿದೆ.

ಇದು ಅತ್ಯಂತ ನಿರಂತರ ವಾಹನ ಸಂಚಾರವಿರುವ ಪ್ರಮುಖ ರಸ್ತೆಯಾಗಿದ್ದು, ದ್ವಿಚಕ್ರ ವಾಹನ ಸವಾರರು ಅಪಘಾತದಿಂದ ತಪ್ಪಿಸಿಕೊಳ್ಳಲು ಇದ್ದಕ್ಕಿದ್ದಂತೆ ವಾಹನಗಳನ್ನು ಪಕ್ಕಕ್ಕೆ ತಿರುಗಿಸುತ್ತಿದ್ದಾರೆ. ಇದರಿಂದಾಗಿ ಇತರೆ ವಾಹನಗಳಿಗೆ ಡಿಕ್ಕಿಯಾಗುವ ಹಾಗೂ ಪ್ರಾಣಾಪಾಯ ಉಂಟಾಗುವ ಭೀತಿ ಹೆಚ್ಚಾಗಿದೆ.

ಸಾರ್ವಜನಿಕರ ಹಿತದೃಷ್ಟಿಯಿಂದ, ದಯವಿಟ್ಟು ಈ ಸ್ಥಳವನ್ನು ಶೀಘ್ರವಾಗಿ ಪರಿಶೀಲಿಸಿ ರಸ್ತೆ ಗುಂಡಿಯನ್ನು ತಕ್ಷಣವೇ ಮುಚ್ಚಿ ದುರಸ್ತಿಗೊಳಿಸಬೇಕಾಗಿ ವಿನಂತಿಸಿಕೊಳ್ಳುತ್ತೇನೆ.

ಧನ್ಯವಾದಗಳೊಂದಿಗೆ,
[ನಿಮ್ಮ ಹೆಸರು]
[ನಿಮ್ಮ ಮೊಬೈಲ್ ಸಂಖ್ಯೆ]

---

**Where to file**
1. Civic helpline: 1533 (unverified, please confirm on the official site)

*(Note: Official app/portal and social media channels are currently not available in our verified system.)*

---

**If nothing happens**
1. Ward-level engineer
2. Zonal joint commissioner
3. Corporation commissioner

---

Would you like me to save a copy of this complaint locally for your records?

[usage] model requests: 4, input tokens: 11369, output tokens: 795
```


### Example with a photo

Genuine run on 2026-10-24 with `gemini-3.5-flash-lite` (`python smoke_test.py --image <photo> "..."`), after the data was marked verified for testing. Output is unedited apart from trailing whitespace.

**Input photo:** a large pile of uncleared mixed waste spread across a commercial street, with a garbage auto parked beside it and shop signs in the background. *(The photo is not included in the repository because it isn't the contributor's own image.)*

**Input text:**
```
mahadevpura, garbage is piled up becase nobody picked it up since days
```

**Output:**
```
[tool call] list_issue_types({})
[tool call] find_department({'issue_type': 'garbage'})
[tool call] get_filing_channels({'authority_id': 'city_corporation'})
**Issue:** Uncleared garbage / black-spot (ಕಸದ ರಾಶಿ)
**Responsible:** Bengaluru city corporation (Greater Bengaluru Authority, formerly BBMP), Solid Waste Management (SWM)
**Location:** Mahadevapura (Note: Please provide a specific road name or nearby landmark when filing so authorities can locate the spot faster.)
**Severity:** High, because a large accumulation of mixed waste is blocking a public roadway.

**Draft complaint (English)**
**Subject:** Urgent clearance of accumulated garbage pile in Mahadevapura

Dear Sir/Madam,

I am writing to report a major uncleared garbage black-spot in the Mahadevapura area, near Mumtaz Sanitary Stores as seen in the photo.

A large pile of mixed waste has accumulated directly on the road and has not been cleared for days. This uncleared garbage is blocking passage and poses significant hygiene and public health risks to residents and commuters passing through the area.

I request you to kindly arrange for immediate clearance and disposal of this garbage pile, and to ensure regular waste collection in this area.

Thank you.

[Your name]
[Your phone number]

**Draft complaint (ಕನ್ನಡ)**
**ವಿಷಯ:** ಮಹದೇವಪುರದಲ್ಲಿ ಸಂಗ್ರಹವಾಗಿರುವ ಕಸದ ರಾಶಿಯನ್ನು ತಕ್ಷಣ ತೆರವುಗೊಳಿಸುವ ಬಗ್ಗೆ.

ಮಾನ್ಯ ಅಧಿಕಾರಿಗಳೇ,

ನಾನು ಮಹದೇವಪುರ ಪ್ರದೇಶದಲ್ಲಿ (ಮುಂಬಾಜ್ ಸ್ಯಾನಿಟರಿ ಸ್ಟೋರ್ಸ್ ಹತ್ತಿರ) ರಸ್ತೆಯಲ್ಲಿ ಬಿದ್ದಿರುವ ದೊಡ್ಡ ಪ್ರಮಾಣದ ಕಸದ ರಾಶಿಯ ಬಗ್ಗೆ ದೂರು ನೀಡಲು ಬಯಸುತ್ತೇನೆ.

ಇಲ್ಲಿ ಹಲವಾರು ದಿನಗಳಿಂದ ಕಸವನ್ನು ವಿಲೇವಾರಿ ಮಾಡದೆ ರಸ್ತೆಯಲ್ಲೇ ಸಂಗ್ರಹಗೊಂಡಿದೆ. ಇದರಿಂದಾಗಿ ದಾರಿಯಲ್ಲಿ ಓಡಾಡುವ ಸಾರ್ವಜನಿಕರಿಗೆ ತೊಂದರೆಯಾಗುತ್ತಿದ್ದು, ಅನಾರೋಗ್ಯದ ಭೀತಿ ಎದುರಾಗಿದೆ.

ದಯವಿಟ್ಟು ಈ ಕಸದ ರಾಶಿಯನ್ನು ತಕ್ಷಣ ತೆರವುಗೊಳಿಸಿ, ಈ ಪ್ರದೇಶದಲ್ಲಿ ನಿಯಮಿತವಾಗಿ ಕಸ ಸಂಗ್ರಹಣೆ ಮಾಡುವಂತೆ ಕ್ರಮ ಕೈಗೊಳ್ಳಬೇಕಾಗಿ ವಿನಂತಿ.

ಧನ್ಯವಾದಗಳು.

[ನಿಮ್ಮ ಹೆಸರು]
[ನಿಮ್ಮ ದೂರವಾಣಿ ಸಂಖ್ಯೆ]

**Where to file**
1. Civic helpline: 1533 (verified)
2. Sahaaya grievance app / portal (not yet available, please confirm on the official site)
3. Official X (Twitter) handle (not yet available, please confirm on the official site)

**If nothing happens**
- Ward-level engineer / health inspector
- Zonal joint commissioner
- Corporation commissioner

Would you like me to save a copy of this complaint?

[usage] model requests: 4, input tokens: 16605, output tokens: 621
```

What this shows: the issue was identified from the photo, a landmark was taken from a visible shop sign, the vague location was flagged, and nothing was added that a photo can't show (e.g. smell). Note the Kannada transliteration of the shop name is slightly off ("ಮುಂಬಾಜ್"), and "(verified)" appears only because the data is marked verified for testing.
---

## How to Test

All commands run from `agents/namma-civic-agent/` with the virtual environment active.

### 1. Automated tests (offline, no API key, about 1 second)

Checks the tools and the integrity of the routing data (every issue maps to a known authority, unknown inputs and invalid severities are rejected, unverified contacts carry a warning, drafts save correctly, the instruction contains no ADK template placeholders) and the contact-detail guardrail (invented phone numbers, URLs, emails and handles are removed, while known helplines, addresses, dates and details the user gave are kept).

```bash
pytest
# expected: 20 passed
```

### 2. Smoke test with a live model (needs `GOOGLE_API_KEY`)

Run each scenario below and compare against the expected behaviour. **Wait about a minute between runs** on the free tier (see Known Limitations).

```bash
python smoke_test.py "<message>"
```

| # | Message | Expected |
| :-- | :-- | :-- |
| 1 | `Pothole on 80 Feet Road, Koramangala 4th Block, been there 2 weeks` | `pothole` → city corporation, Roads / Engineering |
| 2 | `Streetlight off for a week on 12th Main, HSR Layout Sector 6` | `streetlight` → city corporation, **Electrical** (not BESCOM) |
| 3 | `A power line snapped and is sparking near Jayanagar 4th Block bus stand` | Reply **starts** with keep-away advice and 112; `electrical_hazard` → BESCOM; severity critical |
| 4 | `Sewage overflowing from a manhole on CMH Road, Indiranagar` | `sewage_overflow` → BWSSB |
| 5 | `Garbage is piling up` (no location) | Agent asks for the location instead of drafting |
| 6 | `What's the weather today?` | Agent explains it only handles civic issues |

For every reply, also check:
- three tool calls appear before the answer (`list_issue_types`, `find_department`, `get_filing_channels`);
- no phone number, URL or handle appears that isn't in `namma_civic_agent/data/authorities.json`;
- contacts with `"verified": false` carry the "(unverified …)" label (with the testing data all entries are `true`, so no label is expected; set one to `false` to check this);
- the last line shows token usage (about 4 requests, roughly 11k input and 1k output tokens).

On the free tier's daily limit (about 5 complaints), you may not be able to run all six scenarios in one day; spread them out or use a paid key.

### 3. Photo test in the web UI

```bash
adk web
```
Open http://localhost:8000, choose `namma_civic_agent`, attach a photo, and add a location. Try:
- photos of a pothole, garbage and a broken footpath: each should get the right category;
- a photo with no civic issue (e.g. a selfie or food): the agent should say so and not draft a complaint;
- a blurry or dark photo: the agent should ask for a clearer photo or a description.

The web UI also shows each tool call and its result alongside the conversation.

### Troubleshooting

| Symptom | Fix |
| :-- | :-- |
| `429 RESOURCE_EXHAUSTED` mentioning `PerMinute` | Free-tier per-minute limit. Wait about a minute and retry. |
| `429 RESOURCE_EXHAUSTED` mentioning `PerDay` | Free-tier daily limit (20 requests, about 5 complaints). Wait until it resets (the error says when), use a paid tier, or set `MODEL_NAME=gemini-3.5-flash-lite` in `.env` (separate quota; all test scenarios pass on it). |
| `ERROR: ... requires a different Python` during `pip install` | `google-adk` needs Python 3.11+. Recreate the venv with a newer Python. |
| `unsupported image format: .avif` | Convert to JPEG: `sips -s format jpeg photo.avif --out photo.jpg` (macOS) or any image editor. |
| `adk: command not found` | Activate the virtual environment (`source .venv/bin/activate`). |
| `ModuleNotFoundError: namma_civic_agent` | Run commands from `agents/namma-civic-agent/`, not from the repo root. |
| `namma_civic_agent` not listed in `adk web` | Same as above: start `adk web` from `agents/namma-civic-agent/`. |
| `API key not valid` / auth errors | Check `GOOGLE_API_KEY` in `.env` and that `GOOGLE_GENAI_USE_ENTERPRISE=0`. |

---

## Known Limitations

- **Routing data is marked verified for testing only.** All entries in `data/*.json` are set to `"verified": true` so the agent can be demoed, but none has been checked against an official source yet (`source` is `null` everywhere). Bengaluru's civic bodies were recently restructured (BBMP was reorganised under the Greater Bengaluru Authority), and helplines, portals and responsibilities change. **For production, verify every entry and add more details as required** (see the note at the top of this README).
- **Several channels are placeholders.** Portal URLs and social handles that haven't been researched yet are `null`. The agent reports them as "not yet available" rather than guessing.
- **No automatic filing.** City grievance portals don't offer public APIs, so the user must submit the draft themselves.
- **Location is free text.** The agent does not yet resolve a location to a ward or zone, or read GPS from photo EXIF data.
- **Free-tier rate limits.** One complaint takes about 4 model requests (one per tool step plus the final reply). At the time of testing, the Gemini free tier allowed 5 requests per minute and **20 requests per day** for the default model, i.e. roughly **5 complaints per day**. Exceeding either fails with `429 RESOURCE_EXHAUSTED`. For heavier testing, use a paid tier or switch `MODEL_NAME` to a model with a higher free quota.
- **Kannada quality depends on the model.** Have a native speaker review drafts before relying on them.
- **The guardrail is pattern-based.** It catches phone numbers, URLs, emails and @handles, but not, for example, an invented office address or officer name; those are covered only by the prompt. In streaming mode, partial text may be shown before the final filtered reply.
- **Classification can be wrong**, especially for ambiguous photos (e.g. storm drain vs sewer). Always review the draft.
- **Photo input has had limited testing.** One real street photo has been tested so far (see the photo example). Accuracy on night-time, blurry or ambiguous photos is unknown. AVIF images are not accepted by the Gemini API; convert them to JPEG first.
- **Tested on:** macOS (Python 3.12, `google-adk` 2.13). Offline tests pass. Live text runs: all six How to Test scenarios except #4 (sewage) passed on `gemini-3.5-flash-lite` with the current prompt; scenarios 1–3 also passed on `gemini-3.5-flash` with an earlier version of the prompt. One real photo (garbage) tested on `gemini-3.5-flash-lite`. Linux and Windows untested.

---

## Security & Privacy Considerations

- **Secrets Handling**: The API key is read from `.env`, which is git-ignored. Only `.env.example` with placeholders is committed.
- **Data Privacy**: Photos and messages are sent to the Gemini API for processing. Avoid uploading photos that show faces, licence plates or other personal details you don't want shared. Saved drafts go to `complaints/`, which is git-ignored.
- **Safety**: The agent executes no shell commands or code and makes no network calls of its own. Its only side effect is writing a Markdown file when the user asks to save a draft. Its instructions forbid identifying or blaming individuals, inventing contact details or facts, following instructions embedded in photos, and drafting false or harassing complaints. Contact details are additionally enforced in code by `guardrails.py`. Prompt-level rules depend on the model following them; they are tested manually, not automatically.

---

## Future Improvements

- [ ] Verify all routing data against official sources and record each source.
- [ ] Resolve location to ward and zone, and include the corporator or MLA.
- [ ] Read GPS coordinates from photo EXIF metadata.
- [ ] Follow-up reminders and escalation drafts when a complaint is overdue.
- [ ] Duplicate detection for repeated reports of the same issue.
- [ ] Telegram or WhatsApp bot interface.

---

## License

*This project is contributed under the repository's open-source license.*
