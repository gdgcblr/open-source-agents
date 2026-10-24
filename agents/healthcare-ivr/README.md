# Healthcare IVR

> An AI receptionist for a hospital's phone line. It answers callers in English or Hindi, tells them about timings, specialities and doctors, and books, finds and cancels outpatient appointments. A dashboard shows live calls, recordings transcribed by speaker, the AI cost of every call, and how many bookings turn into visits.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Reception lines are busiest when staff are needed at the desk, and most calls are routine: is the OPD open, which doctor sees heart patients, book me for Wednesday, cancel my appointment. Missed calls mean missed patients, and hospitals need to know whether an AI line pays for itself.
- **Intended Users**: developers building voice agents for clinics and hospitals, and hospital operations teams who want routine calls handled and measured.

### How a call goes
1. The receptionist answers: "Hello, welcome to the hospital. Would you like to continue in English or Hindi?" If the caller picks neither, it asks again; after 3 such answers it says goodbye and hangs up.
2. It asks for the patient's name, age, gender, phone number and symptoms, one at a time.
3. If the caller names a doctor on the roster, it uses them; if not, it says so and offers to suggest one. If asked for a suggestion, it picks the speciality for the symptoms (shoulder pain → Orthopaedics) and a doctor from it.
4. It offers that doctor's next free time. If that doesn't suit, it asks for a preferred time and offers that time or the next free one after it.
5. Appointments must be within 72 hours. If nothing works in that window, it apologises and hangs up.
6. It reads the details back and books only when the caller agrees, then gives a booking reference.

### Key Features
- **Answers real phone calls** through Twilio and the [Deepgram Voice Agent API](https://developers.deepgram.com/docs/voice-agent). Callers can interrupt mid-sentence.
- **Speaks English and Hindi**, and understands callers who mix the two.
- **Books, finds and cancels appointments** in its own database, only after the caller confirms. The patient's age, gender, phone number and symptoms are kept with the appointment and left out of logs and the call timeline.
- **Live dashboard**: follow a call as it happens, with a timeline of everything the receptionist did.
- **Recordings transcribed by speaker** with Deepgram diarization after every call.
- **Cost and conversions**: the AI cost of each call, and a funnel from calls to bookings to attended visits. Revenue is counted from attended visits only.
- **Editable hospital information and doctor schedules**, applied from the next call.
- **Guardrails**: confirmation before any change, the language and 72-hour rules enforced in code, the patient's name required to look up or cancel a booking, a per-call booking cap and a call time limit. See [docs/guardrails.md](docs/guardrails.md).

---

## Technical Stack

- **Language & Runtime**: Python 3.13 (backend), TypeScript 6 on Node.js 24 (frontend)
- **Agent Framework / Core Library**: Deepgram Voice Agent API with client-side function calling, bridged to Twilio Media Streams by a FastAPI WebSocket server; SQLAlchemy 2 (async) with SQLite; React 19, Vite 8 and Tailwind CSS 4 for the dashboard
- **Models**: Claude Sonnet 5 (`claude-sonnet-5`) as the receptionist, run by Deepgram (no separate LLM key); Deepgram Flux Multilingual for speech recognition; Deepgram Flux voices `flux-priya-en` (Indian English) and `flux-anjali-hi` (Hindi); Deepgram Nova-3 for transcribing recordings
- **External APIs / Tools**: Twilio Programmable Voice, Deepgram, ngrok (local tunnel)

---

## Architecture & Data Flow

```
Caller ──► Twilio ──► FastAPI bridge ◄──► Deepgram Voice Agent (speech-to-text → Claude → voice)
                          │                       │ function calls
                          │                       ▼
                          │               reception tools ──► SQLite (appointments, calls)
                          ├──► live feed ──► React dashboard (server-sent events)
Twilio recording ────────►└──► Deepgram diarization ──► transcript by speaker
```

Twilio streams the call's audio to the backend, which relays it to Deepgram. When the LLM wants to set the language, find a free time, book, look up or cancel, Deepgram asks the backend to run that function. The backend checks the request against the rules, writes to the database, and sends the result back. Everything that happens is pushed to the dashboard live. After the call, Twilio's recording is transcribed by speaker. Details: [docs/architecture.md](docs/architecture.md).

---

## Prerequisites

**Accounts**
- [Deepgram](https://console.deepgram.com/signup) API key (required; the free credit is enough to try it). It pays for speech recognition, the voices and the LLM.
- To answer phone calls: a [Twilio](https://www.twilio.com/try-twilio) account with a voice-capable number, and a free [ngrok](https://ngrok.com/signup) account.

**Tools**: GNU Make, Git, [uv](https://docs.astral.sh/uv/) (it installs Python 3.13 for you), and Node.js 24 LTS (22.22+ also works). Optional: Docker with Compose v2 for `make docker-up`, and ngrok for `make tunnel`.

Install them once for your system:

**macOS**
```bash
xcode-select --install          # Git and Make
brew install uv node ngrok      # needs Homebrew: https://brew.sh
```

**Linux (Ubuntu / Debian)**
```bash
sudo apt update && sudo apt install -y make git curl
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash   # then reopen the terminal
nvm install 24
```
For ngrok, follow [ngrok.com/download](https://ngrok.com/download).

**Windows**: the Makefile needs a Unix shell, so run the project in WSL 2.
1. In PowerShell as Administrator, run `wsl --install -d Ubuntu`, then restart.
2. Open **Ubuntu** and follow the Linux steps above. Clone the repository inside WSL (for example under `~/`), not under `/mnt/c`, so installs and hot reload stay fast.
3. For `make docker-up`, install Docker Desktop and turn on its WSL integration for Ubuntu.

Browsers on Windows reach the dashboard at `http://localhost:5173` as usual.

If you'll use ngrok, connect it to your account once with the authtoken from the ngrok dashboard: `ngrok config add-authtoken <token>`.

---

## Installation & Setup

1. **Go to the project directory** in your clone of the repository:
   ```bash
   cd agents/healthcare-ivr
   ```

2. **Set everything up**: checks your tools, creates `.env` from `.env.example`, and installs the backend and frontend dependencies.
   ```bash
   make setup
   ```

3. **Add your settings** to `.env`: at least `DEEPGRAM_API_KEY` and a `DASHBOARD_PASSWORD` of your own. Then check them:
   ```bash
   make check-env
   ```

`make help` lists every command.

---

## Configuration & Environment Variables

Set these in `.env`. Every variable is also described in [.env.example](.env.example).

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `DEEPGRAM_API_KEY` | Yes | *None* | Deepgram key for the voice agent and transcription |
| `DASHBOARD_PASSWORD` | Yes | *None* | Dashboard password (HTTP Basic auth). The example value is rejected |
| `DASHBOARD_USERNAME` | No | `admin` | Dashboard username |
| `TWILIO_ACCOUNT_SID` | For calls | *empty* | Twilio Account SID |
| `TWILIO_AUTH_TOKEN` | For calls | *empty* | Twilio auth token, used to verify webhooks and download recordings |
| `PUBLIC_BASE_URL` | For calls | `http://localhost:8000` | Public HTTPS URL Twilio uses to reach the backend (from `make tunnel`), without a trailing slash |
| `HOSPITAL_DIR` | No | `knowledge/sahyadri-deccan` | Folder that seeds the hospital and doctors on first start. See [docs/hospital-data.md](docs/hospital-data.md) |
| `AGENT_LLM_MODEL` | No | `claude-sonnet-5` | LLM Deepgram runs for the receptionist. `claude-haiku-4-5` is faster and cheaper |
| `BOOKING_WINDOW_HOURS` | No | `72` | Appointments must start within this many hours; if nothing works, the call ends |
| `MAX_LANGUAGE_ATTEMPTS` | No | `3` | Answers to "English or Hindi?" that are neither, before the call ends |
| `MAX_CALL_MINUTES` | No | `15` | The receptionist says goodbye and hangs up at this length |
| `MAX_BOOKINGS_PER_CALL` | No | `3` | Most appointments one call can book |

<details>
<summary>All other variables</summary>

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `RECORD_CALLS` | No | `true` | Record calls so they can be transcribed by speaker |
| `TWILIO_VALIDATE_SIGNATURE` | No | `true` | Reject webhooks without a valid `X-Twilio-Signature`. Keep this on |
| `HOSPITAL_TIMEZONE` | No | `Asia/Kolkata` | IANA timezone for the agent's local time and appointment dates |
| `AGENT_LLM_PROVIDER` | No | `anthropic` | Deepgram-managed LLM provider (`anthropic`, `open_ai`, `google`) |
| `AGENT_PROMPT` | No | built-in | Replaces the receptionist instructions. The safety rules, local time, hospital information and doctors are always added |
| `AGENT_GREETING` | No | built-in | First thing the receptionist says. Keep the recording notice |
| `DEEPGRAM_LISTEN_MODEL` | No | `flux-general-multi` | Speech recognition model. Use `flux-general-en` for an English-only line |
| `DEEPGRAM_LANGUAGE_HINTS` | No | `en,hi` | Languages that bias `flux-general-multi` |
| `DEEPGRAM_SPEAK_MODEL` | No | `flux-priya-en` | English voice |
| `DEEPGRAM_SPEAK_MODEL_HINDI` | No | `flux-anjali-hi` | Hindi voice |
| `DEEPGRAM_DIARIZE_MODEL` | No | `nova-3` | Model that transcribes recordings by speaker |
| `DEEPGRAM_DIARIZE_LANGUAGE` | No | `multi` | Recording language: `multi` for mixed Hindi and English, or one language such as `en` |
| `VOICE_AGENT_USD_PER_MINUTE` | No | `0.163` | Deepgram Voice Agent price per minute: `0.163` for `claude-sonnet-5`, `0.075` for Standard-tier models such as `claude-haiku-4-5` |
| `TRANSCRIPTION_USD_PER_MINUTE` | No | `0.0052` | Nova-3 price per audio minute: `0.0052` multilingual, `0.0043` for one language |
| `MAX_UPLOAD_MB` | No | `100` | Largest audio file the dashboard accepts |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./data/reception_calls.db` | SQLAlchemy async database URL |
| `RECORDINGS_DIR` | No | `./data/recordings` | Where call audio is stored |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

</details>

---

## How to Run

**Locally**, with hot reload:
```bash
make dev
```
Open http://localhost:5173 and sign in with your dashboard username and password. The API runs on http://localhost:8000.
- **Calls**: live calls at the top, then every past call with its recording, transcript, timeline and cost.
- **Appointments**: upcoming and past bookings. Mark visits as attended or no-show here.
- **Hospital**: spend, conversions and revenue, plus the information and doctors the receptionist uses.

**To answer phone calls**, add your Twilio values to `.env`, then in a second terminal:
```bash
make tunnel
```
Put the `https://…` URL it prints into `PUBLIC_BASE_URL` in `.env`, restart `make dev`, and point your Twilio number's voice webhook at `https://<your-tunnel>/api/twilio/voice`. Step by step, plus how to use numbers you already have: [docs/phone-setup.md](docs/phone-setup.md).

**With Docker** (dashboard on http://localhost:8080):
```bash
make docker-up      # build and start
make docker-logs    # follow the logs
make docker-down    # stop; calls are kept in a Docker volume
```

After pulling changes to the database models, run `make reset-db`. This deletes local calls and appointments.

---

## Example Input & Output

What the receptionist's functions receive and return during a call: a genuine run against the Sahyadri roster on Saturday 24 October 2026 at 2:42 PM, for a caller with shoulder pain whom the receptionist steered to Orthopaedics.

```
>> set_language {"language": "ta"}
{ "status": "not_supported", "message": "Only English and Hindi are available. Ask again: English or Hindi?" }

>> set_language {"language": "hi"}
{ "language": "hi", "message": "Reply in Hindi from now on. Write in Devanagari script." }

>> find_slot {"doctor_name": "Amruta Khare"}
{ "doctor": "Dr. Amruta Khare", "department": "Orthopaedics", "date": "2026-10-27", "time": "10:00",
  "day": "Tuesday, 27 October 2026", "spoken_time": "10:00 AM" }

>> find_slot {"doctor_name": "Amruta Khare", "date": "2026-10-27", "time": "11:00"}
{ ... "time": "11:00", "spoken_time": "11:00 AM", "requested_time_free": true }

>> book_appointment {"doctor_name": "Dr. Amruta Khare", "date": "2026-10-27", "time": "11:00",
                     "patient_name": "Sunita Patil", "patient_age": 47, "patient_gender": "female",
                     "patient_phone": "+919822045678", "symptoms": "Right shoulder pain for two weeks",
                     "caller_confirmed": true}
{ "status": "booked", "reference": "9MGSBX", "doctor": "Dr. Amruta Khare", "department": "Orthopaedics",
  "day": "Tuesday, 27 October 2026", "time": "11:00 AM", "patient_name": "Sunita Patil", ... }

>> find_slot {"doctor_name": "Amruta Khare", "date": "2026-10-31", "time": "10:00"}
   (the backend hangs up after the receptionist's goodbye)
{ "status": "outside_booking_window", "message": "That time is more than 72 hours away. Appointments can
  only be booked within the next 72 hours. Apologise, explain that, and say goodbye in one short sentence.
  The call ends after that." }
```

At the default rates, a 3-minute call costs about $0.49 in voice-agent time plus $0.016 to transcribe. More examples, including three wrong language answers ending a call, lookups and cancellations: [docs/examples.md](docs/examples.md).

---

## How to Test

```bash
make test     # backend (pytest) and frontend (Vitest)
make lint     # ruff, oxlint and TypeScript
make check    # both, as CI would run them
```

The tests need no API keys: Deepgram and Twilio are replaced with fakes. They cover the scheduling rules and the 72-hour window, every guardrail, and full scripted calls: booking, switching to Hindi, hanging up after three unsupported languages, and the time limit. They also cover live updates, hospital editing, analytics and the dashboard pages.

With Twilio connected, check by phone:
1. Answer "Hindi". It should switch to the Hindi voice and ask for the patient's name, age, gender, phone number and symptoms, one at a time.
2. Say your shoulder hurts and ask it to suggest a doctor. It should pick Orthopaedics, offer the next free time, and book only after you agree.
3. Ask for a doctor who isn't on the roster. It should say so and offer to suggest one.
4. Ask for a time next week. It should explain the 72-hour limit, say goodbye and hang up.
5. Answer "Tamil" three times. It should ask again twice, then say goodbye and hang up.
6. Describe chest pain. It should send you to the emergency number instead of booking.
7. Call again, ask to cancel, and give the patient's name and the reference.

---

## Known Limitations

- **Sample data**: the Sahyadri facts come from the hospital's public website, but the doctors and their schedules are fictional. Never connect this configuration to a public number. Details: [docs/hospital-data.md](docs/hospital-data.md).
- **Standalone bookings**: appointments live in this app's database. There's no hospital system integration, no holidays or doctor leave, and rescheduling means booking the new time, then cancelling the old one.
- **English and Hindi only**: Deepgram's multilingual speech recognition doesn't cover Marathi yet. Each voice speaks one language, so the voice changes when the receptionist switches.
- **Prompt-based safety rules**: emergency handling, no medical advice and staying on topic depend on the LLM following its instructions. The rules that change data are enforced in code.
- **Not yet verified on live calls**: the call flow is tested with fakes of Deepgram and Twilio. Voice quality, Hindi pronunciation and the timing of the time-limit goodbye still need checking on a real call.
- **Estimated costs**: from Deepgram's list prices; Twilio's charges aren't included.
- **One instance**: the live feed is in-process, and SQLite tables are created without migrations.
- **Platforms**: developed and tested on macOS (Apple silicon). Linux, and Windows through WSL 2, are expected to work but are untested.

---

## Security & Privacy Considerations

- **Secrets handling**: credentials come from `.env` (gitignored) or environment variables, are held as secrets in memory, and are never logged. The backend refuses to start with the example dashboard password.
- **Data privacy**: callers share health information. Call audio goes to Deepgram, which passes the conversation to the LLM provider (Anthropic by default). Recordings, transcripts and bookings are stored locally in `backend/data/`. This project is not certified for HIPAA, India's DPDP Act or similar rules; review agreements with Deepgram, Twilio and the LLM provider before handling real patients. Calls are recorded, and the default greeting says so.
- **Safety**: the agent runs no shell commands or code. The LLM can only call five functions, and the code enforces confirmation, validation, ownership and privacy checks, a booking cap and a time limit. Full list and remaining risks: [docs/guardrails.md](docs/guardrails.md).
- **Access**: Twilio webhooks are verified by signature, and the media stream needs a per-call HMAC token. The dashboard uses HTTP Basic auth. Serve it over HTTPS outside your machine, and remember that anyone with the password can change what the receptionist tells callers.

---

## Future Improvements

- [ ] SMS or WhatsApp confirmations and reminders to reduce no-shows
- [ ] Import attended visits from the hospital's system instead of marking them by hand
- [ ] User accounts, roles and an audit log for the dashboard
- [ ] Holidays and doctor leave; a single reschedule action
- [ ] Warm transfer to a person or the emergency desk; Marathi once Deepgram supports it
- [ ] Postgres, migrations and a shared message broker for running several instances

---

## License

*This project is contributed under the repository's open-source license.*
