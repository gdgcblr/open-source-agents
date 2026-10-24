# Architecture

How a call flows through the Healthcare IVR, what's stored, and where the code lives.

## Data flow

```
                        ┌────────────────────────── FastAPI backend ──────────────────────────┐
Caller ──► Twilio ───── │ POST /api/twilio/voice     validate signature → TwiML <Stream>       │
 (any of your numbers)  │                                                                       │
             └─ audio ─►│ WS /api/twilio/media-stream ◄──► Deepgram Voice Agent                 │
                        │   prompt: rules + local time + hospital + doctors   (from database)   │
                        │   FunctionCallRequest ──► reception tools ──► appointments            │
                        │   turns, events, "who's talking" ──► live feed ──┐                    │
                        │                                                  ▼                    │
Dashboard (React) ─────►│ GET /api/calls/{id}/stream   server-sent events ◄┘                    │
                        │ /api/calls · /api/appointments · /api/hospital · /api/analytics       │
                        │                                                                       │
Twilio recording ──────►│ POST /api/twilio/recording-status ─► download → Deepgram diarization  │
                        └───────────────────────────────────────────────────────────────────────┘
```

1. A caller dials one of the hospital's Twilio numbers. Twilio calls `POST /api/twilio/voice`, which checks Twilio's signature and creates the call record, including the caller's and the dialled number. It returns TwiML that opens a bidirectional Media Stream with a per-call HMAC token.
2. The `MediaStreamBridge` loads the hospital and doctors from the database and builds the receptionist's prompt, including the hospital's local time. It opens a Deepgram Voice Agent session with five functions, then relays audio both ways. When Deepgram reports `UserStartedSpeaking`, it sends Twilio a `clear` so the caller can interrupt.
3. Function calls run through `reception_tools`, which validates the arguments, applies the scheduling, privacy and ownership rules, writes to the database, and replies with a `FunctionCallResponse`. Each tool call also writes an event to the call's timeline.
4. Turns, events and Deepgram's `UserStartedSpeaking` / `AgentThinking` / `AgentStartedSpeaking` signals are published to a `LiveFeed`. Anyone viewing the call gets them over `GET /api/calls/{id}/stream`, and the dashboard refreshes the call as they arrive.
5. When the call ends, the bridge prices the Deepgram session (connected seconds × `VOICE_AGENT_USD_PER_MINUTE`) and records a `call_ended` event. Twilio then posts the recording; a background job diarizes it and prices the transcription.
6. Staff record outcomes on the Appointments page, and `GET /api/analytics/summary` turns calls, costs and appointment outcomes into the conversion figures.

## Call script

The prompt walks the receptionist through a fixed script, and the tools enforce the parts that matter:

1. **Language**: the greeting asks "English or Hindi?". The LLM calls `set_language` with the answer. `en` or `hi` switches the voice; any other answer is counted, and the `MAX_LANGUAGE_ATTEMPTS`th one (default 3) asks the bridge to hang up after the goodbye.
2. **Patient details**: name, age, gender, phone number and symptoms, one at a time. `book_appointment` requires all of them and validates each (age 0–120, a fixed list of genders, 7–15 digit phone, symptoms up to 300 characters).
3. **Doctor**: one the caller names, if they're on the roster, or one from the speciality that fits the symptoms.
4. **Time**: `find_slot` returns the doctor's next free time, or the caller's preferred time if it's free, otherwise the next free time after it. A time beyond `BOOKING_WINDOW_HOURS` (default 72), or no free time inside it, ends the call after the goodbye.
5. **Booking**: read back, explicit yes, `book_appointment`, then the reference.

The patient's age, gender, phone number and symptoms are stored on the appointment. In timeline event data they're replaced with `[private]`, and validation errors name the field without repeating its value.

## Languages

Speech recognition uses Deepgram Flux Multilingual (`flux-general-multi`) with `en` and `hi` hints, so it understands English, Hindi and callers who mix them. The receptionist starts in English. When the caller speaks or asks for Hindi, the LLM calls `set_language`. The bridge then sends Deepgram an `UpdateSpeak` with the Hindi voice, before the function result, so the reply that follows uses the new voice. It also saves the call's language. Recordings are transcribed with Nova-3 in `multi` mode.

The receptionist doesn't switch automatically on every turn, because callers who mix Hindi and English would make it flip back and forth.

## Ending calls

When a tool decides the call should end (unsupported language, or nothing within the booking window), it records an `agent_ended_call` event and asks the bridge to hang up. The LLM's reply to that function result is its goodbye. Once Deepgram reports `AgentAudioDone` for it, the bridge sends Twilio a `mark`, waits for the echo, and hangs up through Twilio's REST API.

A timer also runs alongside each call. At `MAX_CALL_MINUTES`, the bridge records a `time_limit_reached` event and sends Deepgram an `InjectAgentMessage` (behaviour `interrupt`, which is never refused) with a goodbye in the call's language. After Deepgram's `AgentAudioDone`, it sends Twilio a `mark` and waits, for at most 20 seconds, for Twilio to echo it back, which means the goodbye has played. It then hangs up through Twilio's REST API. That skips the TwiML fallback message that closing the stream would trigger.

## Database

SQLite through async SQLAlchemy. The file is `backend/data/reception_calls.db` locally, or lives in the `app-data` volume in Docker. Tables are created on startup, and calls left "in progress" by a crash are closed on startup.

| Table | Holds |
| :--- | :--- |
| `calls` | One row per phone call or upload: caller and dialled number, language (`en` or `hi`), Twilio call SID, timing, audio file, transcription status, and the cost estimate (`agent_seconds`, `agent_cost_usd`, `transcription_cost_usd`) |
| `transcript_turns` | The live conversation: each receptionist and caller turn |
| `call_events` | The timeline: what the system did during and after the call, with a readable message and the raw function arguments and results |
| `utterances` | The diarized transcript: speaker, start and end time, text and confidence |
| `appointments` | Bookings: reference, doctor, local date and time, the patient's name, phone, age, gender and symptoms, the fee at booking time, and status (`booked`, `completed`, `no_show`, `cancelled`). A partial unique index allows one active booking per doctor per slot |
| `hospital` | The hospital's name and information (markdown), seeded from `HOSPITAL_DIR` |
| `doctors` | The roster with OPD days, hours, slot length and fee. Removed doctors are deactivated, not deleted, and can't be removed while they have upcoming bookings |

Tables are created with `create_all`, which doesn't add new columns to existing tables. After pulling a change to the models, run `make reset-db` (this deletes local data).

## Project layout

```
agents/healthcare-ivr/
├── Makefile                  # every developer task: `make help`
├── docker-compose.yml        # backend + nginx-served frontend
├── .env.example
├── docs/                     # architecture, hospital data, phone setup, guardrails, examples
├── backend/                  # FastAPI app (uv, pytest, ruff)
│   ├── knowledge/            # seed data: sahyadri-deccan/ (default), medcare-sample/
│   ├── app/
│   │   ├── main.py           # app factory; startup seeds the hospital and closes orphaned calls
│   │   ├── models.py         # calls, turns, events, utterances, appointments, hospital, doctors
│   │   ├── routers/          # calls (incl. live stream), appointments, hospital, analytics, twilio
│   │   └── services/         # voice_agent (bridge), reception_tools, appointments, hospital,
│   │                         # hospital_store, events (live feed), costs, deepgram, diarization
│   └── tests/
└── frontend/                 # React dashboard (Vite, Vitest, oxlint)
    └── src/{api,components,hooks,pages,utils}
```
