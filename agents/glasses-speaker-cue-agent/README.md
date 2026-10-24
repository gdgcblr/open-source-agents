# Glasses Speaker Cue Agent

> An AI teleprompter for smart glasses: turns rough talk notes (and optionally a slide photo) into a speaking script that fits your time slot, split into short cues for the lens, so speakers keep eye contact instead of looking down at their notes.

**Quick start** (no glasses needed):
```bash
cd agents/glasses-speaker-cue-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # then set GOOGLE_API_KEY in .env
python main.py --notes examples/notes.txt --minutes 1     # writes out/script.md + out/deck.json
python glasses_preview.py out/deck.json                   # step through the cues: Enter/→ next, ← back, q quit
```
To present from Meta Ray-Ban Display with the Neural Band, see [Full working flow with Meta glasses](#full-working-flow-with-meta-glasses).

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Speakers at meetups, demos and classes lose their place mid-talk. Looking down at a laptop or phone breaks eye contact. Slide speaker notes are long paragraphs that can't be read at a glance. Teleprompters need a fully written script and a fixed screen. And AI-written scripts usually ignore the time slot: ask for 2 minutes and you get 4.
- **Intended Users**: Meetup and hackathon speakers, students and engineers giving demos, non-native English speakers, and people with presentation anxiety or ADHD who need a short reminder rather than a wall of text.

### Key Features
- **Fits your time slot**: the agent measures its own script with a speaking-time tool (150 words/minute) and revises until it is within ±15% of your target. Code caps this at 3 revisions.
- **Fits the lens**: every cue is at most 90 characters (about 3 short lines on Meta Ray-Ban Display). The split is done by code, not trusted to the model.
- **Pacing marks**: each cue has a "say by mm:ss" time so you know if you are running behind.
- **Any of 11 languages**: English, Hindi, Kannada, Tamil, Telugu, Malayalam, Marathi, Bengali, Spanish, French, German.
- **Q&A prep**: the 3 questions the audience is most likely to ask, with one-line answers, shown after the last cue.
- **Optional slide photo**: Gemini reads the slide as extra source material.
- **Guardrails**: blocks secrets in notes, redacts emails and phone numbers, fences notes against prompt injection, and flags numbers or answers that are not in your notes.
- **Works with NeuralLens**: `script.md` pastes straight into the author's NeuralLens app, which shows the cues on Meta Ray-Ban Display and steps through them with the Meta Neural Band. `deck.json` is a superset of the app's script JSON.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+ (tested on 3.13)
- **Agent Framework / Core Library**: Google Agent Development Kit (ADK) 2.13; Pydantic for the output contract; FastAPI + uvicorn for the optional HTTP API (`server.py`)
- **Models**: Gemini via Google AI Studio (default `gemini-3.5-flash`; any Gemini model that accepts text and images works, set with `MODEL_NAME`)
- **External APIs / Tools**: Gemini API only. The agent's tool (`estimate_speaking_time`) is a pure Python function.
- **Display (optional)**: NeuralLens-AI (Flutter app) + Meta Wearables Device Access Toolkit for Ray-Ban Display and Neural Band. Not needed to run this project.

---

## Architecture & Data Flow

```
notes.txt (+ slide.png) + --minutes + --language
        │
        ▼
Input guardrails (code)  ── limits, image type, secret blocker, PII redaction, <notes> fence
        │
        ▼
ADK LlmAgent (Gemini) ──► estimate_speaking_time tool ──► fits? ──no──► revise (max 3)
        │                                                  │
        │◄────────────────────────── yes ──────────────────┘
        ▼
Draft JSON (title, sections, Q&A)
        │
        ▼
Output guardrails (code) ── schema check, re-split to ≤ 90-char cues, "say by" times,
        │                     time-fit warning, grounding flags (⚠)
        ▼
out/script.md (## headings)  +  out/deck.json
        │
        ├──► glasses_preview.py   (terminal lens, no hardware)
        └──► NeuralLens app ──► Ray-Ban Display lens, Neural Band next/back
```

The rule throughout: **the LLM proposes, code decides.** The model writes; deterministic code measures time, splits cues and checks facts.

| Module | Responsibility |
| :--- | :--- |
| `glasses_speaker_cue_agent/agent.py` | ADK `root_agent` and the `estimate_speaking_time` tool (revision cap enforced in code) |
| `glasses_speaker_cue_agent/prompts.py` | System instruction and request builder (ported from NeuralLens) |
| `glasses_speaker_cue_agent/guardrails.py` | Input checks, secret blocker, PII redaction, notes fence, grounding flags |
| `glasses_speaker_cue_agent/deck.py` | Output contract (Pydantic), cue building, `script.md` rendering |
| `glasses_speaker_cue_agent/pipeline.py` | The full request pipeline shared by the CLI and the server |
| `server.py` | Token-protected HTTP API (`POST /v1/script`) for apps such as NeuralLens |
| `glasses_speaker_cue_agent/cues.py`, `duration.py` | Cue splitting and speaking-time math (ported from NeuralLens) |
| `main.py` | CLI |
| `glasses_preview.py` | Terminal "lens" preview |

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.11 or newer
- pip
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) (free tier works; see Known Limitations)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/glasses-speaker-cue-agent
   ```

2. **Set up the virtual environment and install dependencies:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Open `.env` in your editor and set `GOOGLE_API_KEY`. `.env` is git-ignored; never commit it.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | Yes | *None* | Gemini API key from Google AI Studio |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | `FALSE` | Keep `FALSE` to use AI Studio rather than Vertex AI |
| `AGENT_TOKEN` | Only for `server.py` | *None* | Shared secret apps send as `X-Agent-Token`; at least 24 random characters (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) |
| `MODEL_NAME` | No | `gemini-3.5-flash` | Gemini model ID; must accept text and images if you use `--slide`. Smaller "lite" models often miss the time target |

---

## How to Run

```bash
# Notes -> out/script.md + out/deck.json
python main.py --notes examples/notes.txt --minutes 2

# Kannada cues, with a slide photo, without Q&A
python main.py --notes examples/notes.txt --minutes 1.5 --language kn --slide my-slide.png --no-qa

# Step through the cues like the Neural Band (Enter/→ next, ← back, q quit)
python glasses_preview.py out/deck.json

# Visual chat UI from ADK (run from this folder; pick glasses_speaker_cue_agent)
adk web
```

| Option | Default | Meaning |
| :--- | :--- | :--- |
| `--notes` | required | Text file with your notes (max 8,000 characters) |
| `--minutes` | `2` | Time slot, 0.5–30 |
| `--language` | `en` | `en hi kn ta te ml mr bn es fr de` |
| `--slide` | none | PNG, JPEG or WebP, max 5 MB |
| `--no-qa` | off | Skip the Q&A section |
| `--keep-pii` | off | Send emails and phone numbers without redacting |
| `--out` | `out` | Output folder |
| `--verbose` | off | Show ADK/Gemini internal logs (full tracebacks) for debugging |

Exit codes: `0` success, `2` invalid input or missing config, `3` blocked by a guardrail, `4` Gemini/API error.

### HTTP server (for apps)
```bash
python server.py                   # http://127.0.0.1:8080, this machine only
python server.py --host 0.0.0.0    # reachable from a phone on the same network
python server.py --port 9000       # different port (default 8080)
```
The server needs `AGENT_TOKEN` in `.env` and refuses to start without it.

`POST /v1/script` with header `X-Agent-Token` and JSON `{"notes": "...", "durationSeconds": 60, "language": "en", "includeQa": true}` returns the same `deck.json` as the CLI. `GET /healthz` returns `{"ok": true}`.

| Status | Meaning |
| :--- | :--- |
| `200` | Deck JSON |
| `400` | Invalid input (empty notes, unsupported language, ...) |
| `401` | Missing or wrong `X-Agent-Token` |
| `411` | No `Content-Length` (chunked uploads are refused) |
| `413` | Body larger than 64 KB |
| `422` | Blocked by a guardrail (e.g. a secret in the notes); nothing was sent to Gemini |
| `422` (schema) | `durationSeconds` outside 30–1800, or malformed JSON |
| `429` | Gemini rate limit or overload, or the server is already handling 2 requests |
| `500` | The server's own config is missing (e.g. `GOOGLE_API_KEY`) |
| `502` | Gemini error or unusable model reply |

### Full working flow with Meta glasses

The agent runs on its own with just a laptop (see the commands above and `glasses_preview.py`). To present from real smart glasses, the full setup is:

**What you need**

| Item | Role | Required? |
| :--- | :--- | :--- |
| Laptop with Python 3.11+ and this project | Runs the agent (CLI or `server.py`) | Yes |
| Gemini API key | Model calls | Yes |
| Meta Ray-Ban Display glasses | Show the cues on the lens | For the glasses flow |
| Meta Neural Band | Hands-free next / back / pause | For the glasses flow |
| Android phone with the NeuralLens app (developer build) | Connects to the glasses through the Meta Wearables Device Access Toolkit and presents the cues | For the glasses flow |
| Phone and laptop on the same trusted network (a phone hotspot works) | Lets the app reach `server.py` | Only for the direct flow (B) |

The NeuralLens app is the author's own Flutter app and is not public yet. Without it, use `glasses_preview.py`, which shows the same cues in the terminal.

**End-to-end flow**
```
You: rough notes + time slot + language
        │
        ▼
Laptop: agent (Gemini) ── writes, measures, revises, splits into ≤ 90-char cues
        │  A: copy script.md        B: app calls POST /v1/script
        ▼
Android phone: NeuralLens app ── turns the script into cues, starts the presentation
        │  (Meta Wearables Device Access Toolkit, Bluetooth)
        ▼
Meta Ray-Ban Display: one cue at a time on the lens
        ▲
Meta Neural Band: next / back gestures, select = pause or resume
```

**Steps**
1. **Set up the hardware once.** Pair the Ray-Ban Display glasses and the Neural Band with the Android phone, and install the NeuralLens developer build. Connect the glasses from inside the app.
2. **Generate the script on the laptop.** Choose one path:
   - **A. Copy-paste (no network setup):** run `python main.py --notes my-notes.txt --minutes 2 --language en`, then copy the contents of `out/script.md` into the NeuralLens editor. The app splits it on the `##` headings into the same cues the agent produced (verified with real English and Kannada outputs: identical cue counts).
   - **B. Direct from the app:** run `python server.py --host 0.0.0.0` with the laptop and phone on the same trusted network. Put `AGENT_URL=http://<laptop-ip>:8080` (find it with `ipconfig getifaddr en0`) and the same `AGENT_TOKEN` in the app's `.env`, then build the app with `flutter run --dart-define-from-file=.env`. In the app, choose a language, enter your notes and tap generate; the request goes through this agent. Check connectivity first by opening `http://<laptop-ip>:8080/healthz` in the phone's browser; it should show `{"ok":true}`. Path B needs the app's agent-backend changes, which are not public yet.
3. **Present.** Press Present in NeuralLens. Each cue appears on the lens. Use the Neural Band to move to the next or previous cue; select pauses or resumes.
4. **If anything fails, fall back to A.** Keep a pre-generated `script.md` loaded in the app, in case the network or Gemini (which can return "overloaded") is unavailable during your talk.

---

## Example Input & Output

### Example Input
[`examples/notes.txt`](examples/notes.txt):
```
Lightning talk at GDG Cloud Bengaluru, FORK. BUILD. MERGE.

- problem: speakers lose their place, look down at laptop, break eye contact
- speaker notes in slides are long paragraphs, can't read at a glance
- AI scripts ignore time: ask for 2 minutes, get 4
...
```

```bash
python main.py --notes examples/notes.txt --minutes 2
```

### Example Output
Real run on 2026-10-24 with `gemini-3.5-flash`, `--minutes 1`:
```
Writing a 1:00 English script with gemini-3.5-flash...
  [time check 1] 1:01 vs target 1:00 -> fits
  [time check 2] 1:01 vs target 1:00 -> fits

NeuralLens: Smart Cues for Live Presentations
1:01 (target 1:00, fits) · 14 cues · 3 Q&A
Wrote out/script.md and out/deck.json
```

`out/script.md` (excerpt):
```
## Eyes on Screen
Have you ever seen a speaker completely lose their audience because they keep staring at their laptop? Traditional speaker notes are huge blocks of text. Even AI tools mess up by giving you a four-minute script for a two-minute talk.

## Meet NeuralLens
That is why I created NeuralLens. It pushes clean, glanceable cues right onto Meta Ray-Ban smart glasses. You can navigate sections using a Neural Band without missing a beat.
...
## Q&A
Q: How does the agent ensure the talk fits the target time?
A: The agent measures speaking time with a tool and revises the script up to three times to hit the target duration.

Q: How much does the Neural Band cost?
A: ⚠ Not in your notes — verify: Pricing details for the Neural Band hardware are not available in the talk notes.
```
The last answer shows the grounding guardrail: the notes say nothing about price, so the answer is marked for the speaker to verify.

`out/deck.json` (first cue):
```json
{"index": 0, "sectionIndex": 0, "heading": "Eyes on Screen", "text": "Have you ever seen a speaker completely lose their audience because they keep staring at", "sayBy": 6, "sayByLabel": "6s", "flags": []}
```

`python glasses_preview.py out/deck.json --print` (first card):
```
╭────────────────────────────────╮
│ Eyes on Screen  1/14           │
│                                │
│ Have you ever seen a speaker   │
│ completely lose their audience │
│ because they keep staring at   │
│                                │
│ say by 6s                      │
╰────────────────────────────────╯
```

**Self-correction in action.** Real run, same notes, `--minutes 1 --language kn`. The first draft was short, so the agent expanded it and checked again:
```
Writing a 1:00 Kannada script with gemini-3.5-flash...
  [time check 1] 48s vs target 1:00 -> outside target, add ~29 words
  [time check 2] 1:06 vs target 1:00 -> fits
```
With the smaller `gemini-3.5-flash-lite`, drafts for a 2-minute slot stayed short (1:26–1:32) even after 3 revisions. The cap stopped the loop and the CLI printed `Warning: Estimated 1:32 vs target 2:00 (outside ±15%).` This is why `gemini-3.5-flash` is the default.

---

## How to Test

Automated tests run offline: no API key and no network needed.

```bash
pytest          # cue splitting, timing, guardrails, deck building, revision cap, preview, HTTP server
ruff check .    # lint
```

Manual end-to-end check:
1. `python main.py --notes examples/notes.txt --minutes 2` prints `[time check N]` lines, then writes `out/script.md` and `out/deck.json`.
2. `python glasses_preview.py out/deck.json --print` shows every cue inside the lens box.
3. Guardrail check: add a fake key line such as `AIza` followed by 35 letters to a copy of the notes and run again. It must stop with `Blocked:` and exit code 3 without sending anything.

---

## Known Limitations

- **Speaking time is an estimate** at 150 words per minute. Real pace varies by speaker and language; Indic-language timing is approximate.
- **Languages without spaces** (Chinese, Japanese, Thai) are not supported, because timing counts space-separated words.
- **Lens width is counted in Unicode code points.** That is conservative for Indic scripts, but the terminal preview's box border can look uneven for them.
- **Grounding check covers digits only.** Models often write numbers as words ("ninety"), and those, like made-up names, are not detected. Review the script before presenting.
- **Secrets inside a slide image are not detected**; only the text notes are scanned.
- **Numbers from a slide can't be verified by code.** With `--slide`, numbers missing from the notes are flagged "check your slide" instead of being treated as invented.
- **Phone redaction matches common formats** (international `+…`, North American, Indian mobile). Other local formats may not be redacted; use `--keep-pii` only when you're sure.
- **Gemini overload (503)**: the client retries, then exits with "temporarily overloaded, try again in a minute".
- **Free-tier rate limits**: Gemini free tier can return 429. The client makes up to 3 attempts on 429/503, then exits with a "wait a minute" message. Each run makes several model calls (one per draft or revision, plus the final answer), so free-tier quotas run out faster than with a single prompt.
- **Model output varies**: if the model ignores the format, the CLI asks once more and then exits with code 4. Runs take about 20–40 seconds. Slower "thinking" models can hit the 60-second per-call timeout.
- **Cue breaks can fall mid-sentence**: a sentence longer than 90 characters with no comma is split at a word boundary, and its tail can share a cue with the next sentence. This matches how the NeuralLens app splits the same script.- Tested on macOS (Python 3.13). Linux should work; Windows is untested (the preview falls back to Enter-based input).

---

## Security & Privacy Considerations

- **Secrets Handling**: The API key is read from `.env` (git-ignored) or the environment and is never printed or logged. Notes are scanned for API keys, tokens and private keys before sending; if any are found, nothing is sent and only the line number is reported.
- **Data Privacy**: Notes and the optional slide image are sent to the Google Gemini API. Emails and phone numbers are redacted first unless you pass `--keep-pii`. Don't use confidential material unless your organisation allows sending it to Gemini.
- **HTTP server**: `server.py` refuses to start without a strong `AGENT_TOKEN`, listens only on `127.0.0.1` unless `--host` is given, checks the token with a constant-time comparison before reading the body, requires `Content-Length` and rejects bodies over 64 KB, runs at most 2 generations at once, applies the same guardrails as the CLI, exposes no API docs, and never logs notes or tokens. It serves plain HTTP: use it only on a trusted network, and don't expose it through a public tunnel.
- **Safety**: The agent cannot run shell commands, write files, browse the web or execute code. Its only tool is a pure function that counts words. Notes are wrapped in a `<notes>` fence that they cannot close, and the instruction treats their contents as material, never as instructions. A code-enforced cap of 3 revisions, which carries over into the one JSON retry, and a limit of 10 model calls per request in total (ADK `max_llm_calls`) prevent runaway loops. Outputs are written only to the `--out` folder.

---

## Future Improvements

- [ ] Capture the slide directly from the glasses camera (Meta Wearables Device Access Toolkit photo capture) instead of passing a file.
- [ ] Deploy `server.py` to Cloud Run (HTTPS, key in Secret Manager) so the app doesn't need a local network or debug-only plain HTTP.
- [ ] Accept a slide image over HTTP (the server currently takes notes only).
- [ ] Rehearsal coach: record a practice run and get missed points, speaking pace and filler words (later via the glasses microphone).
- [ ] Per-language speaking rates.

---

## License

This project is contributed under the repository's open-source license (MIT). The cue-splitting, timing and prompt logic is ported from the author's own NeuralLens app.
