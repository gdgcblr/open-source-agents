# Scam Shield

> A lightweight, multilingual and accessible scam-message checker. You paste, speak, share or screenshot a suspicious SMS or WhatsApp message, and it tells you in your own language whether the message is a scam, why, and what to do next.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Scams like fake KYC, UPI collect requests, parcel re-delivery fees, electricity disconnection, "digital arrest", job/task scams and "Hi Mum, new number" reach millions of people in India every day. The people most at risk, such as elderly people, first-time smartphone users, people with low literacy and people with disabilities, often can't read English well and are on low-end phones with slow networks.
- **Intended Users**: Everyday phone users in India, and the family members who help them. It's also useful for developers who want a reference for a multi-agent ADK pipeline that falls back gracefully when the model is unavailable.

### Key Features
- **Multi-agent analysis (Google ADK + Gemini)**: three investigators (links, payment requests and scam patterns) run in parallel, then a verdict agent writes a structured answer.
- **8 languages**: English, Hindi, Kannada, Tamil, Telugu, Malayalam, Marathi and Bengali, for both the interface and the AI's answer. A "simple words" mode gives shorter, easier answers.
- **Screenshot input**: Gemini reads the screenshot. The browser shrinks it to about 150 KB before upload.
- **Always gives an answer for text**: an instant offline rule check runs in the browser, then the AI result replaces it. With no API key or an AI error, the server falls back to its rule engine.
- **Works on slow networks and offline**: the app shell is about 16.5 KB gzipped, a service worker caches it, and it has no external scripts, fonts or trackers.
- **Accessible**: works keyboard-only, announces the verdict to screen readers, has large-text and high-contrast modes, voice input, read-aloud, a different vibration for each verdict, and respects reduced motion. Lighthouse accessibility score: 100.
- **Safe link checks**: short links (bit.ly, etc.) are expanded with HEAD requests to an allowlist of shortener hosts only, with SSRF protection. The final page is never fetched.
- **Installable PWA**: it can be added to the home screen, and on Android you can share a message from WhatsApp or SMS straight into the app.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+ (tested on 3.12) for the server and agents. Plain HTML, CSS and JavaScript for the frontend, with no build step. Node.js 18+ is only needed to run the browser-rules test.
- **Agent Framework / Core Library**: Google Agent Development Kit (`google-adk` ≥ 2.13): `LlmAgent`, `ParallelAgent`, `SequentialAgent`, `Runner` and `InMemorySessionService`.
- **Models**: Gemini `gemini-3.5-flash-lite` through the Gemini API (free-tier key from Google AI Studio). You can change it with `MODEL_NAME`. Vertex AI is supported with `GOOGLE_GENAI_USE_VERTEXAI=true`.
- **Web server**: FastAPI and Uvicorn.
- **External APIs / Tools**: Gemini API, plus HEAD requests to URL-shortener hosts for link expansion. No database and no other paid services.

More detail on every dependency and browser API is in [docs/TOOLS.md](docs/TOOLS.md).

---

## Architecture & Data Flow

```
                 ┌──────────── Browser (PWA, works offline) ────────────┐
[User: paste /   │ index.html ──► offlineCheck(text)  ──► instant result │
 speak / share / │      │                                                │
 screenshot] ───►│      └──► POST /api/check {text, image, language}    │
                 └──────────────────────┬────────────────────────────────┘
                                        ▼
                       FastAPI server.py (validate, rate limit)
                                        │
                 ┌──── API key set? ────┴──── no key / AI error ────┐
                 ▼                                                  ▼
   ADK SequentialAgent                                    rules_verdict(text)
   ├─ ParallelAgent                                       (tools.py, text only)
   │   ├─ link_investigator    → analyze_links                      │
   │   ├─ payment_investigator → detect_payment_requests            │
   │   └─ pattern_investigator → scan_scam_patterns                 │
   └─ verdict_agent (Gemini, structured output, user's language)    │
                 │                                                  │
                 └──────────────► JSON verdict ◄────────────────────┘
                   {verdict, risk_score, scam_type, summary, red_flags, advice}
```

- Every request uses a temporary session that is deleted after the check. Nothing is stored.
- The message is treated as untrusted. All prompts tell the model never to follow instructions inside it.
- Each AI check makes about **7 model calls** (3 investigators × 2, plus 1 verdict).

Mermaid diagrams, the request sequence, the fallback layers and the scaling limits are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### Project layout

```
agents/scam-shield-agent/
├── README.md               # This file
├── .env.example            # Placeholder configuration (copy to .env)
├── .gitignore
├── requirements.txt
├── server.py               # FastAPI app: /api/check, /api/health, serves the PWA
├── scam_shield/
│   ├── agent.py            # ADK multi-agent pipeline (root_agent)
│   └── tools.py            # Deterministic tools: links, payments, patterns, rules_verdict
├── static/                 # PWA: index.html (UI + offline rules), sw.js, manifest, icon
├── tests/                  # pytest tests, shared rule fixture, Node test for browser rules
├── eval/                   # Labelled datasets, run_eval.py, RESULTS.md (real Gemini runs)
└── docs/                   # ARCHITECTURE.md, TOOLS.md, ACCESSIBILITY.md
```

---

## Prerequisites

- Python 3.10 or newer (tested with 3.12.1 on Windows 11), plus `pip`.
- A **Gemini API key** (optional, free tier is enough): https://aistudio.google.com/apikey. Without a key the app still works in rules-only mode for text, but screenshots need the AI.
- Optional: Node.js 18+ (tested with 22.14) to run the browser-rules test.
- Optional: Chrome on Android to try install, share-to-app and voice input.
- **Windows tip:** `google-adk` installs some files with long paths. If `pip install` fails with `OSError: [Errno 2] No such file or directory ... Long Path support`, clone into a short folder (for example `C:\src`) or [enable long paths](https://pip.pypa.io/warnings/enable-long-paths).

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/scam-shield-agent
   ```

2. **Create a virtual environment and install dependencies:**
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
   cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
   ```
   Open `.env` and paste your key after `GOOGLE_API_KEY=`. To try the app with no key, leave it empty. The server then answers with the rule engine. Any non-empty value turns AI mode on, so don't put placeholder text there.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEYS` | No (needed for AI and screenshots) | *None* | Comma-separated Gemini API keys, any number. Tried in order with automatic failover (see below). If no key is set, the server uses the rule engine only. |
| `GOOGLE_API_KEY` | No | *None* | Older setting, still supported: one key or a comma-separated list. `GEMINI_API_KEY` is also accepted. Its keys are added after the `GOOGLE_API_KEYS` list, skipping duplicates. |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | `FALSE` | Set to `TRUE` to use Vertex AI with Google Cloud credentials instead of an API key. |
| `MODEL_NAME` | No | `gemini-3.5-flash-lite` | Gemini model used by all four agents. It must support tools, structured output and image input. (`gemini-2.5-flash-lite` now returns 404 for new users.) |
| `HOST` | No | `0.0.0.0` | Address the server listens on. |
| `PORT` | No | `8080` | Port the server listens on. |
| `LOG_LEVEL` | No | `info` | Logging verbosity (`debug`, `info`, `warning`, `error`). |
| `RATE_LIMIT_PER_MINUTE` | No | `20` | Checks allowed per client IP per minute (in-memory). |

The real `.env` is git-ignored. Never commit it.

### API key failover

Set several keys in `GOOGLE_API_KEYS` and each check uses the key that last worked. If that key fails, the server tries the next one:

- **Invalid, expired or no permission** (HTTP 400/401/403): the key is turned off until the server restarts.
- **Over quota** (HTTP 429): the key is skipped for the wait time Gemini sends back (60 s if none is given).
- **Server error or timeout**: the next key is tried and the key stays on.
- **Any other error** (for example a bad request): no more keys are tried, because they would fail the same way.

If every key fails, a text check still returns the rule-engine verdict with an `ai_error` field that gives the reason for each key, listed by number. A screenshot-only check returns HTTP 503 with the same message. `/api/health` shows `keys_total` and `keys_available`. Keys are never logged or returned; logs refer to them only as key #1, #2 and so on. Create each key in a **different Google Cloud project**: free-tier quota is per project, so keys from the same project run out together.

---

## How to Run

```bash
# Start the web app and API (from agents/scam-shield-agent with the venv active)
python server.py
# Open http://localhost:8080

# Check the server status ("ai": true means the Gemini key was loaded)
curl http://localhost:8080/api/health

# Check a message from the command line
curl -X POST http://localhost:8080/api/check -H "Content-Type: application/json" \
  -d '{"text": "Your HDFC account will be blocked today. Share the OTP sent to your phone with our officer and install AnyDesk to complete KYC.", "language": "en", "simple": true}'

# Inspect the agent pipeline in the ADK developer UI (needs a key)
adk web .        # then choose "scam_shield"
```

**API** (`POST /api/check`):

| Field | Type | Notes |
| :--- | :--- | :--- |
| `text` | string | Up to 5,000 characters. |
| `image_base64` | string, optional | JPEG, PNG or WebP, up to 1.5 MB after decoding. |
| `image_mime` | string | `image/jpeg` (default), `image/png` or `image/webp`. |
| `language` | string | `en`, `hi`, `kn`, `ta`, `te`, `ml`, `mr` or `bn`. |
| `simple` | bool | `true` gives shorter answers in simple words. |

Errors: `400` (empty or invalid input), `413` (image too large), `429` (rate limit), and `503` (screenshot-only request while AI is unavailable).

---

## Example Input & Output

All outputs below come from genuine runs on 2026-10-24. The full set, including Hindi, screenshot and prompt-injection tests, is in [eval/RESULTS.md](eval/RESULTS.md).

### Example Input
```
Your HDFC account will be blocked today. Share the OTP sent to your phone with our officer and install AnyDesk to complete KYC.
```

### Example Output: AI mode (`gemini-3.5-flash-lite`, simple words on, about 14.5 s)
```json
{
  "verdict": "scam",
  "risk_score": 95,
  "scam_type": "Fake Bank KYC Scam",
  "summary": "This message is a scam. It tries to scare you by saying your bank account will be blocked so you will share your secret OTP and install remote apps.",
  "red_flags": [
    "Threatens that your bank account will be blocked.",
    "Asks you to share your secret OTP.",
    "Tells you to install a screen-sharing app like AnyDesk."
  ],
  "advice": [
    "Do not click or reply.",
    "Block the sender.",
    "Report at 1930 or cybercrime.gov.in."
  ]
}
```

### Example Output: AI mode in Kannada (`"language": "kn"`, same message)
```json
{
  "verdict": "scam",
  "risk_score": 95,
  "scam_type": "ಬ್ಯಾಂಕ್ ಖಾತೆ ಬ್ಲಾಕ್ ಮತ್ತು ಕೆವೈಸಿ ವಂಚನೆ",
  "summary": "ಇದು ಖಾತೆ ಬ್ಲಾಕ್ ಆಗುತ್ತದೆ ಎಂದು ಬೆದರಿಸಿ ಒಟಿಪಿ ಮತ್ತು ರಮೋಟ್ ಆ್ಯಪ್ ಮೂಲಕ ಹಣ ಲಪಟಾಯಿಸಲು ಯತ್ನಿಸುತ್ತಿರುವ ಸ್ಪಷ್ಟ ವಂಚನೆ ಸಂದೇಶವಾಗಿದೆ.",
  "red_flags": ["ಖಾತೆ ಬ್ಲಾಕ್ ಆಗುತ್ತದೆ ಎಂದು ಭಯ ಹುಟ್ಟಿಸುವುದು.", "ಫೋನ್ಗೆ ಬಂದ ಒಟಿಪಿ (OTP) ಕೇಳುವುದು.", "..."],
  "advice": ["ಯಾವುದೇ ಒಟಿಪಿ (OTP) ಅಥವಾ ವೈಯಕ್ತಿಕ ವಿವರಗಳನ್ನು ಹಂಚಿಕೊಳ್ಳಬೇಡಿ.", "...", "ಸೈಬರ್ ವಂಚನೆ ಬಗ್ಗೆ ಕೂಡಲೇ 1930 ಗೆ ಅಥವಾ cybercrime.gov.in ಗೆ ವರದಿ ಮಾಡಿ."]
}
```

### Example Output: rules mode (no API key, `rules_verdict` on the same message)
```json
{"verdict": "scam", "risk_score": 100, "red_flags": ["asks for otp", "remote access app", "account block kyc"]}
```
The API adds `"mode": "rules"` and the time taken. The web app translates these flags into the chosen language.

---

## How to Test

From `agents/scam-shield-agent` with the venv active:

```bash
# 1. Unit and API tests (no key or network needed): 32 tests
pytest -q

# 2. Browser offline rules: loads offlineCheck straight from static/index.html and runs
#    the same shared fixture (tests/rule_cases.json) that pytest uses, so Python and JS rules can't drift
node tests/test_offline_rules.js

# 3. Rule-engine accuracy on labelled data (no key needed)
python eval/run_eval.py --mode rules                                  # original set, 40 messages
python eval/run_eval.py --mode rules --dataset eval/heldout.jsonl     # held-out set, 41 messages

# 4. Full AI pipeline accuracy (needs a key; free tier allows about 2 checks/min, so use a delay)
python eval/run_eval.py --mode agent --delay 20
```

Results measured on 2026-10-24 (Windows 11, Python 3.12.1, Node 22.14):

| Check | Result |
| :--- | :--- |
| `pytest -q` | 32 passed |
| `node tests/test_offline_rules.js` | 20/20 shared rule cases passed |
| Python rules, original set | 40/40 (100%) |
| Python rules, held-out set (written without seeing the rules) | 30/41 (73.2%): caught 14/21 scams, 4/20 false alarms |
| Browser rules, held-out set | 31/41 (75.6%) |
| AI mode | Functional checks pass (screenshot, Kannada, Hindi, simple mode, prompt injection, bad-key fallback). Full-dataset AI accuracy hasn't been measured yet. See [eval/RESULTS.md](eval/RESULTS.md). |
| Accessibility (Lighthouse) | Accessibility 100, Best Practices 100. See [docs/ACCESSIBILITY.md](docs/ACCESSIBILITY.md). |

**Manual check:** run `python server.py`, open http://localhost:8080, paste the example message above, and press **Check**. You should see "⛔ Scam" at once (offline check), then the server's answer.

---

## Known Limitations

- **Rule-engine accuracy is moderate**: 73% on the held-out set. It misses scams written fully in Indic scripts, and some new wordings. For example, "Your electricity will be cut tonight… call officer" is still marked `safe` by the rules. The AI mode is much stronger, but its full-dataset accuracy hasn't been measured yet.
- **Free-tier speed and quota**: each AI check makes 7 model calls and takes about 14.6 s for text (range 5–24 s) and about 23 s for a screenshot. The Gemini free tier allows 15 requests per minute, so the whole server handles **about 2 AI checks per minute**. A one-call design has been proposed in [eval/RESULTS.md](eval/RESULTS.md) but isn't applied.
- **Tokens**: about 4.8k input and 0.6k output tokens per text check, and about 12.4k / 0.7k for a screenshot. Paid-tier cost hasn't been measured.
- **Screenshots need the AI**: without a key they return `503`.
- **Rate limiter** is in memory and per instance. Behind a proxy, all users may share one IP bucket.
- **ADK deprecation warning**: ADK 2.13 warns that `SequentialAgent`/`ParallelAgent` are deprecated. They still work.
- **Platforms tested**: Windows 11 with Python 3.12 and headless Chrome. Linux/macOS setup hasn't been tested. Voice input, read-aloud, install, share-to-app, vibration and TalkBack need a real Android phone and haven't been tested. Offline reload hasn't been verified (see [docs/ACCESSIBILITY.md](docs/ACCESSIBILITY.md)).
- **Translations** were reviewed by an AI reviewer, not by native speakers.
- **Not deployed**: it runs locally only for now.
- **No independent security review** has been done yet.

---

## Security & Privacy Considerations

- **Secrets Handling**: the API key is read from the environment or a local `.env`, which is git-ignored. `.env.example` contains placeholders only. No key is stored in code or sent to the browser.
- **Data Privacy**: messages and screenshots are not stored. Each check uses a temporary session that is deleted afterwards. **In AI mode, the message text and screenshot are sent to Google's Gemini API.** In rules mode, nothing leaves the server except HEAD requests to known URL-shortener hosts. The browser offline check never leaves the device.
- **Safety**: the agent doesn't run shell commands or code.
  - Link expansion only contacts hosts on a fixed shortener allowlist, only with HEAD, and only when every resolved address is public (SSRF protection). Redirects are followed manually (up to 5 hops) and the final page is never fetched.
  - Input is capped at 5,000 characters of text and a 1.5 MB image.
  - Prompts treat the message as untrusted. A prompt-injection test was still judged `scam`.
  - FastAPI's `/docs` pages are disabled.

---

## Future Improvements

- [ ] One-model-call design (run the three tools in Python, then make one verdict call) for about 7× more checks per minute.
- [ ] Measure full-dataset AI accuracy on both datasets.
- [ ] Better rules for scams written fully in Indic scripts, and electricity/"call officer" wording.
- [ ] Test on real Android phones (voice, install, share, TalkBack) and get native-speaker translation reviews.
- [ ] Deploy to Google Cloud Run with the key in Secret Manager and a shared rate limiter.
- [ ] Independent security review.

---

## License

This project is contributed under the repository's open-source license ([MIT](../../LICENSE)). No third-party code was copied in. The dependencies are listed in `requirements.txt` and keep their own licenses.
