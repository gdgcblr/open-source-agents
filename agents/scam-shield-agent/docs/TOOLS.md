# Scam Shield: Tools, Libraries and Services

## Runtime dependencies (`requirements.txt`)

| Item | Version | Used for | Why this choice |
|---|---|---|---|
| **Google Agent Development Kit** (`google-adk`) | ≥ 2.13.0 | `LlmAgent`, `ParallelAgent`, `SequentialAgent`, `Runner`, `InMemorySessionService`; `adk web` for debugging | Built-in parallel and sequential composition, session state with `output_key` hand-off, function tools from plain Python functions, and structured output with Pydantic. Note: ADK 2.13 shows a deprecation warning for `SequentialAgent`/`ParallelAgent`; they still work |
| **Google GenAI SDK** (`google.genai`, installed with ADK) | via ADK | `types.Content`, `types.Part` (text and image bytes), `GenerateContentConfig` | Same SDK ADK uses; sends screenshots inline as image parts |
| **Pydantic** (installed with FastAPI and ADK) | via deps | `Verdict` output schema; `CheckRequest` validation with length limits | One schema serves both the model's structured output and API validation |
| **FastAPI** | ≥ 0.115 | HTTP API, static file serving, gzip middleware | Async (works with ADK's async runner), automatic request validation, small footprint |
| **Uvicorn** | ≥ 0.30 | ASGI server (`python server.py`) | Standard FastAPI server; reads `HOST`/`PORT` for container platforms |
| **python-dotenv** | ≥ 1.0 | Loads `.env` for local development | Keeps the API key out of code and out of git |
| **pytest** | ≥ 8.0 | Unit and API tests (`tests/test_tools.py`, with FastAPI `TestClient`) | Standard Python test runner |

## Python standard library (no extra dependencies)

| Module | Used for | Why |
|---|---|---|
| `re` | Link, UPI-ID, phone and phrase matching | Deterministic, fast, no model cost |
| `urllib.parse`, `urllib.request` | Parsing URLs; HEAD requests to shortener hosts with redirects disabled | Keeps the tool module dependency-free, so it is easy to test and audit |
| `ipaddress`, `socket` | Raw-IP detection; checks that shortener hosts resolve only to public addresses | SSRF protection |
| `collections.deque` | Sliding-window rate limiter | Simple and O(1) per request |
| `base64`, `uuid`, `time`, `logging` | Image decoding, session ids, timing, logs | — |

## Models and external services

| Service | Used for | Why |
|---|---|---|
| **Gemini** via the Gemini API (or Vertex AI with `GOOGLE_GENAI_USE_VERTEXAI=true`) | All four agents. Default model `gemini-3.5-flash-lite`, configurable with `MODEL_NAME` | Low-cost, fast model with tool calling, structured output, image input and Indian-language output. A free-tier key is available from Google AI Studio. Latency and tokens: see [eval/RESULTS.md](../eval/RESULTS.md) |
| **URL-shortener hosts** (bit.ly, tinyurl.com and others on a fixed list) | Revealing the real destination of shortened links | HEAD requests only; the final page is never contacted |
| **National cybercrime helpline 1930 and cybercrime.gov.in** | Shown in the app and required in AI advice for clear scams | The official reporting channels in India |
| **Google Cloud Run** (planned, not yet deployed) | Hosting the single container | HTTPS by default (needed for PWA features), scales to zero, reads `PORT` |

## Browser platform APIs (no frameworks, no external scripts)

| API | Used for | Why |
|---|---|---|
| Service Worker + Cache Storage | Offline app shell | App opens and runs offline checks with no network |
| Web App Manifest + `share_target` | Install to home screen; "Share → Scam Shield" on Android | Users check a message straight from WhatsApp or SMS |
| Web Speech API: `SpeechRecognition` | Voice input in Indian locales | For users who find typing hard |
| Web Speech API: `speechSynthesis` | Read the verdict aloud | For low-vision and low-literacy users |
| `createImageBitmap` + `<canvas>` | Shrinks screenshots to ≤ 1024 px JPEG before upload | Small uploads on slow networks |
| `navigator.vibrate` | Distinct vibration per verdict | Feedback that does not rely on sight |
| `localStorage` | Remembers language and accessibility settings | No account or server storage needed |
| CSS media queries: `prefers-color-scheme`, `prefers-reduced-motion`, `forced-colors` | Dark mode, no spinner animation when reduced motion is requested, Windows high-contrast support | Respects the user's OS settings |

Plain HTML, CSS and JavaScript in one file was chosen over a framework to keep the shell at about
16 KB gzipped and to avoid any third-party script.

## Development and evaluation tools

| Tool | Used for |
|---|---|
| `eval/run_eval.py` | Accuracy, recall and false alarms in `rules` or `agent` mode on any JSONL dataset (`--dataset`, `--delay` for free-tier limits) |
| `eval/dataset.jsonl`, `eval/heldout.jsonl` | Labelled messages. The held-out set was written without seeing the rules |
| Node.js + `tests/offline_rules.js`, `tests/test_offline_rules.js` | Loads `offlineCheck` straight from `index.html` (no copy), measures it on a dataset, and runs the shared fixture `tests/rule_cases.json` (the same fixture pytest uses for `tools.py`) |
| `adk web` | Interactive inspection of the agent pipeline and its state |
| Chrome DevTools / Lighthouse | Offline, throttling and accessibility checks (see [ACCESSIBILITY.md](ACCESSIBILITY.md)) |
