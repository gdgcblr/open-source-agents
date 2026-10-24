# Weekly Focus Coach

> A text based Google ADK agent that helps people turn important goals into realistic next steps and see how their time and outcomes are progressing.

## Overview

### Problem Statement & Intended Users

Procrastination can make it hard to start work that matters. Weekly Focus Coach gives users a supportive check-in, tracks one or two weekly goals, and suggests a manageable action based on the user's actual progress and available time. It is intended for people working toward goals such as interview preparation, focused study, reading, or exercise.

### Key Features

- Record up to two weekly goals with priorities, clear success criteria, and optional longer term goal context.
- Track time spent separately from completed outcome milestones.
- Log and correct activities with a date, duration, accomplishment, and morning/afternoon/evening label.
- Show an independent text progress bar for each goal.
- Suggest a realistic next focus and save a plan only after the user approves it.

The first version accepts text. Voice check-ins, scheduled reminders, and a website dashboard are future extensions.

## Technical Stack

- **Language & Runtime:** Python 3.12 (Python 3.10+ supported)
- **Agent Framework / Core Library:** Google Agent Development Kit (ADK) 2.13.0
- **Models:** Gemini Flash via Google AI Studio
- **Data Storage:** Local, atomically replaced JSON file; Pydantic validates data
- **External APIs / Tools:** Gemini API; ADK's development chat interface

## Architecture & Data Flow

```text
Text check-in
     |
     v
Gemini through ADK <----> six Python function tools
                              |             |
                    validation/metrics   local JSON
                              |
     <---- response with per-goal progress bars and a next step
```

The deterministic models, calculations, and JSON store are separate from the ADK agent and can be wrapped by a future website backend. The ADK browser interface is for local development and demonstration, not a production website.

## Data Model

`weekly_focus_coach/models.py` defines JSON serializable, validated records:

- **WeeklyGoal:** title, week start, priority, success criteria, time or milestone metric, optional long term goal and target date.
- **Milestone:** a measurable outcome with an ID, reported completion state, and completion note.
- **Activity:** date, description, duration, period of day, optional goal link, and accomplishment.
- **FocusPlan:** date, available minutes, proposed actions, deferred items, and approval time. Only explicitly approved plans are saved.
- **FocusState:** schema version, revision, goals, activities, and plans.

Minute goal bars use logged minutes against the goal's target. Milestone goal bars use completed milestones against all planned milestones. An activity log never completes a milestone. Each goal keeps its own bar so progress on a secondary goal cannot obscure the primary goal.

The JSON file defaults to `data/focus.json` in the project folder. Set `FOCUS_DATA_PATH` to choose another location. Writes use a temporary file and atomic replace; the file is created with owner-only permissions. Malformed data is reported without overwriting the original. JSON is ignored by Git.

## Prerequisites

- Python 3.12 recommended; Python 3.10 or later supported.
- `uv` for an isolated environment and dependency installation.
- A Google AI Studio API key to run live Gemini conversations. Offline tests do not need a key.
- Terminal and browser for ADK's local development interface.

## Installation & Setup

From the repository root:

```bash
cd agents/weekly-focus-coach
uv venv --python 3.12 .venv
```

Install from public PyPI. `--no-config` avoids a globally configured package index:

```bash
uv --no-config pip install \
  --python .venv/bin/python \
  --default-index https://pypi.org/simple \
  -r requirements.txt
```

Set up the local key file and add the key:

```bash
cp .env.example weekly_focus_coach/.env
```

Edit `weekly_focus_coach/.env` and replace the placeholder `GOOGLE_API_KEY`. This secret file and the focus data are excluded from Git.

## Configuration & Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `GOOGLE_GENAI_USE_VERTEXAI` | Select Google AI Studio instead of Vertex AI. | `FALSE` |
| `GOOGLE_API_KEY` | Google AI Studio key used for live Gemini conversations. | Required for live use |
| `MODEL_NAME` | Compatible Gemini model name. | `gemini-3.5-flash-lite` |
| `FOCUS_TIMEZONE` | Timezone used to determine the current date and week. | `UTC` |
| `FOCUS_DATA_PATH` | Optional location for the JSON data file; relative paths use the project root. | `data/focus.json` |

Keep the real API key only in `weekly_focus_coach/.env`. Do not place it in source files, terminal transcripts, or committed documentation. Offline tests do not require the key.

## How to Run

Activate the environment and run the ADK web development interface from the project root:

```bash
source .venv/bin/activate
adk web --port 8000
```

Open `http://localhost:8000` and choose `weekly_focus_coach` from the agent list. The interface accepts text messages. Local agent and Gemini setup is required for a live conversation.

## Available Agent Tools

| Tool | What it does |
|---|---|
| `set_weekly_goal` | Creates a time based or milestone based weekly goal. |
| `log_activity` | Records activity time and accomplishment separately. |
| `correct_activity` | Edits a prior log without adding a duplicate. |
| `update_goal_progress` | Sets the user's reported completed milestone IDs. |
| `get_weekly_metrics` | Returns individual progress bars, logs, and saved plans. |
| `save_focus_plan` | Saves a selected action after the user confirms it. |

## Example Conversation

The demo scenario has six of eight focused work outcomes completed and one of four interview preparation milestones completed, with two days left. The main goal's progress remains visible even though many smaller tasks are done.

The following summarizes a live-tested conversation (responses shortened for readability):

```text
User: Set two goals: interview preparation with four milestones, and focused work with eight sessions.
Coach: Interview preparation is 0/4 and focused work is 0/8.
User: I practiced arrays for 45 minutes this evening and completed the review arrays milestone.
Coach: Interview preparation is 1/4 with 45 minutes logged; focused work is 0/8.
User: I completed focus sessions 1 through 6.
Coach: Focused work is 6/8; interview preparation is 1/4 and at risk with two days remaining.
User: I have 20 minutes free. What should I focus on?
Coach: Practice one behavioral answer for 20 minutes. Would you like to save that plan?
User: I only have 10 minutes now.
Coach: Outline one behavioral answer using STAR for 10 minutes; defer the other work. Would you like to save this revised plan?
User: Yes.
Coach: Saved the 10-minute plan.
```

The live run also verified that the adjusted plan was not saved before approval and that the saved action fit within the user's revised 10-minute availability.

## How to Test

Run the deterministic suite without a model API key:

```bash
source .venv/bin/activate
PYTHONPATH=. python -m unittest discover -s weekly_focus_coach/tests -v
```

Tests cover JSON round trips and file permissions, weekly goal limits, separate time and outcome progress, per goal bars, corrections, approval before saving, malformed data preservation, and invalid dates and IDs.

To check the agent entry point and tool wiring, run `adk web --port 8000` and try the example prompts. A live Gemini conversation requires a valid API key and network access.

Live end-to-end test: on 2026-10-24, the ADK Runner used `gemini-3.5-flash-lite` to create two goals, log 45 minutes separately from milestone progress, update milestone progress to 1/4 and 6/8, revise a 20-minute recommendation to fit 10 minutes, request approval, save the approved plan, and verify the result. The workflow assertions passed using an isolated temporary JSON file.

Captured terminal output from a live Gemini run on 2026-10-24. Prompts and model replies are reproduced as entered and returned; Markdown line breaks are preserved. Trailing spaces at line ends are omitted.

```text
USER INPUT 1:
For the week starting 2026-10-19, set two milestone goals. Priority 1: Interview preparation, with these four milestones: Review arrays; Practice behavioral answers; Complete a mock interview; Review feedback. Success means completing all four milestones. Priority 2: Focused work, with eight milestones named Focus session 1 through Focus session 8. Success means completing all eight sessions.
TOOLS 1: ['set_weekly_goal', 'set_weekly_goal', 'get_weekly_metrics']
MODEL RESPONSE 1:
I've successfully set up your two weekly goals for the week starting 2026-10-19!

Here is where we stand as of **2026-10-24** (with **2 days remaining** in the week):

1. **Interview preparation** (Priority 1):
   * Progress: `░░░░░░░░░░` 0% (0/4 milestones completed, 0 minutes spent)
   * ⚠️ **At Risk:** With only 2 days remaining, your priority goal is well below 75% complete (0% complete, 4 milestones remaining).

2. **Focused work** (Priority 2):
   * Progress: `░░░░░░░░░░` 0% (0/8 milestones completed, 0 minutes spent)

Since time is tight, let's take a small, manageable step to get the momentum going. Would you like to start with **"Review arrays"** for Interview preparation today? If so, how many minutes do you have available?
---
USER INPUT 2:
Log 45 minutes of interview preparation this evening. I reviewed arrays and completed the Review arrays milestone.
TOOLS 2: ['log_activity', 'update_goal_progress', 'get_weekly_metrics']
MODEL RESPONSE 2:
Great job logging your time and completing that first milestone!

Here is where we stand as of **2026-10-24** (with **2 days remaining**):

1. **Interview preparation** (Priority 1):
   * Progress: `██░░░░░░░░` 25% (1/4 milestones completed, 45 minutes spent)
   * ⚠️ **At Risk:** With 2 days remaining, this priority goal is below 75% complete (currently at 25% with 3 milestones remaining).

2. **Focused work** (Priority 2):
   * Progress: `░░░░░░░░░░` 0% (0/8 milestones completed, 0 minutes spent)

You've made a fantastic start on your interview prep. For your next step, would you like to tackle **"Practice behavioral answers"**? How many minutes do you have available for it?
---
USER INPUT 3:
I completed Focus sessions 1 through 6. Mark those six milestones complete for my Focused work goal.
TOOLS 3: ['update_goal_progress', 'get_weekly_metrics']
MODEL RESPONSE 3:
That is a huge push on your focused work!

Here is where we stand as of **2026-10-24** (with **2 days remaining**):

1. **Interview preparation** (Priority 1):
   * Progress: `██░░░░░░░░` 25% (1/4 milestones completed, 45 minutes spent)
   * ⚠️ **At Risk:** With 2 days remaining, your priority goal is below 75% complete (currently at 25% with 3 milestones remaining).

2. **Focused work** (Priority 2):
   * Progress: `████████░░` 75% (6/8 milestones completed, 0 minutes spent)

You're making incredible progress. Since Interview preparation is your priority goal and remains at risk with only 2 days left, let's keep our momentum going there. Would you like to tackle **"Practice behavioral answers"** next? If so, how many minutes can you set aside for it?
---
USER INPUT 4:
How is my week going? I have 20 minutes available today. What should I focus on?
TOOLS 4: ['get_weekly_metrics']
MODEL RESPONSE 4:
Here is how your week looks as of **2026-10-24**, with just **2 days remaining**:

1. **Interview preparation** (Priority 1):
   * Progress: `██░░░░░░░░` 25% (1/4 milestones completed, 45 minutes spent)
   * ⚠️ **At Risk:** With only 2 days left, your priority goal is below 75% complete (currently at 25% with 3 milestones remaining and a gap of 3 milestones).

2. **Focused work** (Priority 2):
   * Progress: `████████░░` 75% (6/8 milestones completed, 0 minutes spent)

With **20 minutes available today**, the best place to focus is your priority goal, **Interview preparation**. Since practicing a full mock interview or reviewing feedback takes longer, your 20 minutes is a great fit for starting on **"Practice behavioral answers"**.

Would you like to use your 20 minutes today to work on practicing behavioral answers?
---
USER INPUT 5:
I only have 10 minutes now. Revise the recommendation to fit 10 minutes and tell me what to defer. Do not save it yet.
TOOLS 5: []
MODEL RESPONSE 5:
Given that you only have **10 minutes** available today and **2 days remaining** in the week, your priority goal (**Interview preparation**, currently at 25%) remains at risk.

To respect your 10-minute window, here is a realistic adjustment:
* **Action:** Spend those 10 minutes drafting bullet points for a couple of common behavioral interview questions to jump-start **"Practice behavioral answers"**.
* **Deferred Items:** Defer completing the entire behavioral practice session and the mock interview/feedback review to your remaining time tomorrow.

Does this 10-minute plan sound good to you? Once you agree, we can get it saved!
---
USER INPUT 6:
Yes, save that 10-minute plan.
TOOLS 6: ['save_focus_plan', 'get_weekly_metrics']
MODEL RESPONSE 6:
Your 10-minute focus plan has been successfully saved!

Here is where we stand as of **2026-10-24** (with **2 days remaining**):

1. **Interview preparation** (Priority 1):
   * Progress: `██░░░░░░░░` 25% (1/4 milestones completed, 45 minutes spent)
   * ⚠️ **At Risk:** With 2 days remaining, your priority goal is below 75% complete (currently at 25% with 3 milestones remaining).

2. **Focused work** (Priority 2):
   * Progress: `████████░░` 75% (6/8 milestones completed, 0 minutes spent)

You've got your plan locked in. Whenever you're ready, spend those 10 minutes drafting bullet points for your behavioral interview questions!
---
FINAL STATE: goals=2 activities=1 approved_plans=1
```

## Known Limitations

- Local JSON storage supports a single local user and one running application process; it is not a shared or concurrent database.
- The agent requires Gemini network access for conversation; deterministic storage and calculations can be exercised offline.
- Progress is based on user reported entries and milestones; the agent does not independently assess interview readiness.
- The local ADK development interface is for testing and demonstration, not production deployment.
- Push reminders, voice input, accounts, a hosted API, and a web dashboard are not implemented.
- Tested on macOS with Python 3.12; other operating systems are unverified.

## Security & Privacy Considerations

- Store the Gemini key only in `weekly_focus_coach/.env`; do not commit it.
- Activity, goal, and plan data stay in the local JSON file. Gemini receives conversation messages and tool context needed to answer; do not enter sensitive personal information.
- The JSON data file is ignored by Git and written with owner-only file permissions.
- The agent has no arbitrary shell or file tools. Its Python functions can only operate on the configured focus data store.
- The local ADK development interface should only be exposed on a trusted development machine.

## Future Improvements

- [ ] Accept spoken check-ins and let users correct extracted logs.
- [ ] Add scheduled, opt-in reminders that prompt users to begin a small next action.
- [ ] Provide a web API and dashboard using the same goal and progress models.
- [ ] Support other goal units and explicit weekly milestone templates.
- [ ] Generate personalized weekly milestones from longer-term goals and adapt them as progress changes.
- [ ] Replace single user JSON storage with a database for a hosted multi-user service.
- [ ] Add user selected commitment blocks and available time schedules.

## License

This project is contributed under the repository's open-source license.
