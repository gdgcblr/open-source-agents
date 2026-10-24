# Android Automation Agent (Google ADK)

An autonomous agent that turns a natural-language request such as *"Open Brave and search for youtube.com"* into verified UI actions on a connected Android emulator or physical device.

The agent is the **reasoning/planning layer**. All Android interaction goes through the existing, deterministic **execution layer** in [`tools/android-ui-automation`](../../tools/android-ui-automation); nothing from it is duplicated here.

> **Status:** written against the documented Google ADK Python API. The guard logic and the adapter's integration with the real automation layer are covered by the smoke tests. The end-to-end acceptance test (a real Gemini model driving a real device) must be run on a machine with `adb`, an emulator/device and a Gemini API key; see [Acceptance test](#acceptance-test).

## 1. What the agent does

For each request it: understands the goal → observes the device → performs **one** action → observes the result → decides the next step, adapting when the UI is not what it expected, until the goal is verified or it cannot continue reliably. It then reports success or failure in a fixed, concise format.

Key behaviours (defined in `src/prompts.py`, with the limits enforced in code):

- Never assumes UI state; inspects when useful, not repeatedly.
- Prefers semantic selectors (resource id → exact text → content description → hint → text-contains → class/index); raw coordinates only as a last resort.
- Separates *action executed* from *intent achieved*; verifies important results.
- Treats inconclusive text read-back (`TEXT_VERIFICATION_FAILED`) as inconclusive, not as failure.
- Bounded retries and a hard cap on tool calls per request.
- Does not take destructive or irreversible actions unless the user explicitly asks.

## 2. Architecture

```text
User
 ↓
Google ADK Agent            src/agent.py        (root_agent, Gemini, instruction)
 ↓
Planning / Reasoning        src/prompts.py      (system instruction)
                            src/callbacks.py    (logging, retry + tool-call limits)
 ↓
Android Automation Tools    src/tools.py        (thin adapter, one function per primitive)
 ↓                          tools/android-ui-automation  (AndroidAutomation facade)
ADB
 ↓
Android Device
```

```text
agents/android-automation-agent/
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── src/
│   ├── __init__.py     # exposes root_agent to ADK
│   ├── __main__.py     # python -m src "<task>"
│   ├── agent.py        # root agent + one-shot runner
│   ├── prompts.py      # system instruction
│   ├── tools.py        # ADK tool adapter over AndroidAutomation
│   ├── callbacks.py    # structured logging + retry/tool-call guards
│   └── config.py       # environment configuration
└── tests/
    └── test_smoke.py
```

`callbacks.py`, `config.py`, `__main__.py` and `tests/` are small additions to the requested layout: they keep logging/guards, settings and the smoke test out of the four required modules.

## 3. Prerequisites

- Python **3.10+** (required by ADK)
- Android platform-tools (`adb`) on `PATH`, or `ADB_PATH` set
- An Android emulator or physical device with USB debugging enabled
- The `tools/android-ui-automation` project (already in this repository)
- A Gemini API key (Google AI Studio) **or** a Google Cloud project with Vertex AI
- The target app installed on the device (e.g. Brave: `com.brave.browser`)

## 4. Android device setup

1. Install platform-tools and check `adb version`.
2. **Emulator:** start an AVD (with the target app installed) and confirm `adb devices` lists `emulator-5554  device`.
   **Physical device:** enable Developer options → USB debugging, connect, accept the RSA prompt; `adb devices` must show `device` (not `unauthorized`).
3. Keep the screen on and unlocked while the agent runs.
4. If several devices are connected, set `ANDROID_DEVICE_ID` to the serial.

## 5. Google ADK setup

```bash
pip install google-adk        # or: pip install -r requirements.txt
```

Credentials, either:

- **Gemini API key:** create one at <https://aistudio.google.com/apikey> and put it in `.env` as `GOOGLE_API_KEY`.
- **Vertex AI:** `gcloud auth application-default login`, then set `GOOGLE_GENAI_USE_VERTEXAI=TRUE`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` in `.env`.

Docs: <https://adk.dev/get-started/python/>.

## 6. Environment configuration

```bash
cd agents/android-automation-agent
cp .env.example .env     # then fill in your credentials; .env is git-ignored
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `GOOGLE_API_KEY` | – | Gemini API key (or use the Vertex AI variables) |
| `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` | – | Vertex AI alternative |
| `AGENT_MODEL` | `gemini-flash-latest` | Gemini model; must be supported by your ADK version |
| `AGENT_MAX_RETRIES` | `2` | Retries allowed for an **identical** failing call (enforced) |
| `AGENT_MAX_TOOL_CALLS` | `40` | Hard cap on tool calls per user request (enforced) |
| `AGENT_LOG_LEVEL` | `INFO` | Logging level |
| `AGENT_LOG_TYPED_TEXT` | `false` | Log text typed into the device (off by default) |
| `ANDROID_AUTOMATION_PATH` | `../../tools/android-ui-automation` | Location of the automation project |
| `ADB_PATH`, `ANDROID_DEVICE_ID` | `adb`, *(empty)* | ADB executable and device serial |
| `COMMAND_TIMEOUT_SECONDS`, `UI_WAIT_TIMEOUT_SECONDS` | `30`, `5` | Automation timeouts |

Real environment variables take precedence over `.env`. No credentials are stored in source.

## 7. Installation

```bash
cd agents/android-automation-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

The automation layer has no third-party dependencies; `adb` is its only external requirement.

## 8. How the agent connects to the existing automation tool

`src/tools.py` loads `tools/android-ui-automation/src` **unmodified** as a package named `android_ui_automation` (both projects have a top-level package called `src`, so the alias avoids the clash), builds one `AndroidAutomation` instance from this project's settings, and exposes each primitive as a plain Python function that ADK turns into a Gemini tool:

```python
def launch_app(package_name: str) -> dict:
    """Launch an Android app by its package name ..."""
    return _run("launch_app", package_name=package_name)
```

- Results are the layer's `ActionResponse.to_dict()`: `success`, `action`, `message`, `data`, and on failure `error: {code, details}`; error codes and diagnostics are preserved.
- Light shaping only: UI elements are compacted to save tokens; an `agent_note` is added for some codes (for example `TEXT_VERIFICATION_FAILED` is explained as inconclusive); tool calls are serialised with a lock.
- One adapter-level helper, `find_installed_package(name_hint)`, runs `pm list packages` through the layer's own ADB client so the agent can turn "Brave" into a package name. It is read-only and contains no planning logic.
- There are no composite tools such as "launch Brave and search"; the agent composes primitives itself.

## 9. How to run the agent

From `agents/android-automation-agent/`:

```bash
# Interactive terminal chat
adk run src

# Browser UI (shows each tool call and result); pick "src" in the agent list
adk web --port 8000

# One-shot, prints the final report
python -m src "Open Brave and search for youtube.com"
```

Development logging goes to stderr as one JSON line per event (`agent_decision`, `tool_call`, `tool_result`, `tool_refused`).

Smoke tests (no device or API key needed; live checks run automatically when a device is connected):

```bash
python -m unittest discover -s tests -v
```

### Acceptance test

With an emulator/device running and Brave installed:

```bash
python -m src "Open Brave and search for youtube.com."
```

Expected: the agent checks the device, resolves/launches Brave, inspects the UI, finds the address field, enters `youtube.com`, presses Enter, observes the resulting page, confirms navigation, and reports success.

## 10. Example user commands

- "Open Brave and search for youtube.com."
- "Open the Calculator app and compute 12 × 7."
- "Go to Settings and open the Wi-Fi screen." *(navigation only; it will not change settings)*
- "Open Chrome, go to example.com and tell me the page title."

## 11. Example execution flow

```text
User: Open Brave and search for youtube.com.

agent_decision  → check the device first
tool_call       is_device_connected                   ✓ connected
tool_call       find_installed_package(brave)         ✓ com.brave.browser
tool_call       get_current_activity                  ✓ launcher in foreground
tool_call       launch_app(com.brave.browser)         ✓ process started
tool_call       get_ui_hierarchy                      ✓ address bar url_bar seen
tool_call       input_text(resource_id=url_bar, ...)  ✓ (or inconclusive read-back → observe)
tool_call       press_enter                           ✓ key sent
tool_call       verify_state(expected_text=YouTube)   ✓ expected state seen

Task completed successfully.
Actions performed: ...
Final state: Brave is showing youtube.com
```

(Illustrative: the real sequence is decided from tool responses at run time.)

## 12. Known limitations

- **Not yet verified end to end in this repository's build environment** (no device, no API key, no network access to install ADK). Run the acceptance test on your machine.
- The agent cannot see screenshots (out of scope for v1); it observes the UI only through the UI hierarchy. Web content in browsers is exposed only as far as Android accessibility exposes it.
- Text input is printable ASCII only (`adb shell input text`).
- `click_element` supports `text`, `resource_id`, `content_description`, `class_name`, `index`; there is no click-by-hint or click-by-substring (the agent uses `find_element` first).
- The retry guard counts *identical* failing calls; changing a selector is a new call and is bounded only by `AGENT_MAX_TOOL_CALLS`.
- App-name → package resolution relies on substring matching of package names (`pm list packages`), not app labels.
- Package names such as `com.brave.browser` depend on the installed build (beta/nightly differ).
- ADK callback hooks (`before_tool_callback`, `after_tool_callback`, `after_model_callback`) follow ADK's documented signatures; if a future ADK version changes them, adjust `src/callbacks.py`.
- A single device and a single agent at a time.

## 13. Future improvements

- Screenshot-based reasoning and OCR as optional fallbacks.
- Bug-reproduction and behavioural-testing modes built on the same tool layer.
- Persisted task traces and a replayable run log.
- Click-by-hint / fuzzy selectors in the automation layer.
- App label lookup (not just package names) and install helpers.
- Multi-device support and a multi-agent split (planner / executor / verifier) if needed.
