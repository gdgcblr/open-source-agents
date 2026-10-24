# Namma Civic Agent

> Snap a photo of a civic problem in Bengaluru and get a ready-to-send complaint, in English and Kannada, addressed to the right authority.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Potholes, garbage black-spots, broken streetlights, sewage overflows and open manholes often go unreported. Residents don't know which authority handles what (city corporation, BESCOM, BWSSB or traffic police), where to file, or how to write a complaint that gets acted on. Many also assume, wrongly, that streetlights belong to BESCOM or that every drain belongs to BWSSB.
- **Intended Users**: Bengaluru residents, resident welfare associations (RWAs) and civic volunteers.

### Key Features
- **Photo understanding**: Classifies a photo (or text description) into one of 17 civic issue categories using a multimodal model.
- **Grounded routing**: The authority, department, helplines and escalation path come from curated local JSON data, not from the model's memory, so the agent cannot invent phone numbers.
- **Bilingual drafts**: Writes a structured complaint in English and natural Kannada.
- **Safety first**: Critical hazards (live wires, open manholes) get keep-away advice and the emergency number before anything else.
- **Honest about data**: Contact details not yet verified are labelled as such in every reply.
- **Drafts, never files**: The user stays in control of submission.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+
- **Agent Framework**: [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) 2.x
- **Models**: Gemini 3.5 Flash (default, configurable via `MODEL_NAME`). Any Gemini model with image input works.
- **External APIs / Tools**: Gemini API only. Routing data is local JSON.

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
│   └── data/
│       ├── issue_types.json  # 17 issue categories -> authority + department
│       └── authorities.json  # Authorities -> helplines, portals, escalation path
├── tests/test_tools.py       # Offline tests (no API key needed)
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
   python3.11 -m venv .venv
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

---

## Example Input & Output

> 🚧 **TODO before opening the PR:** replace this section with a transcript from a genuine run using one of your own photos (save the photo in `examples/`). CONTRIBUTING.md requires examples to come from real runs.

### Example Input
```
[photo: examples/<your-photo>.jpg]
"Near Indiranagar 100 Feet Road, opposite the metro pillar. It's been there 5 days."
```

### Example Output
```
<paste the agent's real reply here>
```

---

## How to Test

**Automated (offline, no API key):** checks the tools and the integrity of the routing data.
```bash
pytest
```

**Manual (needs an API key):**
1. Run `adk web` and open the UI.
2. Upload photos of different issue types, e.g. a pothole, garbage, a dark streetlight, and a snapped wire.
3. Check that:
   - each photo is classified into the right category;
   - streetlights route to the city corporation, not BESCOM;
   - the electrical hazard reply starts with safety advice and 112;
   - no phone number or URL appears that isn't in `data/authorities.json`;
   - unverified contacts carry the "(unverified …)" label;
   - a non-civic photo (e.g. a selfie) is politely rejected.

---

## Known Limitations

- **Routing data is not yet verified.** Every entry in `data/*.json` currently has `"verified": false`. Bengaluru's civic bodies were recently restructured (BBMP was reorganised under the Greater Bengaluru Authority), and helplines, portals and responsibilities change. Until the data is checked against official sources, the agent labels contacts as unverified.
- **Several channels are placeholders.** Portal URLs and social handles that haven't been researched yet are `null`. The agent reports them as "not yet available" rather than guessing.
- **No automatic filing.** City grievance portals don't offer public APIs, so the user must submit the draft themselves.
- **Location is free text.** The agent does not yet resolve a location to a ward or zone, or read GPS from photo EXIF data.
- **Kannada quality depends on the model.** Have a native speaker review drafts before relying on them.
- **Classification can be wrong**, especially for ambiguous photos (e.g. storm drain vs sewer). Always review the draft.
- **Tested on:** offline tool tests pass on macOS. End-to-end runs with a live model, and Linux/Windows, are not yet tested.

---

## Security & Privacy Considerations

- **Secrets Handling**: The API key is read from `.env`, which is git-ignored. Only `.env.example` with placeholders is committed.
- **Data Privacy**: Photos and messages are sent to the Gemini API for processing. Avoid uploading photos that show faces, licence plates or other personal details you don't want shared. Saved drafts go to `complaints/`, which is git-ignored.
- **Safety**: The agent executes no shell commands or code and makes no network calls of its own. Its only side effect is writing a Markdown file when the user asks to save a draft. Its instructions forbid identifying or blaming individuals and inventing contact details.

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
