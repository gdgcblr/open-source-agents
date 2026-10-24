# MeetingMind AI — Meeting Summarizer & Action Item Agent

> An open-source, privacy-first Chrome Extension and multi-agent system powered by **Gemma**, **Google Agent Development Kit (ADK)**, **Agent-to-Agent (A2A)** protocol, and **Model Context Protocol (MCP)** to summarize meetings, write per-person to-do lists, schedule calendar reminders, nudge via email for missing deadlines, and save notes directly to Google Drive.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Modern knowledge workers and software teams spend countless hours in virtual meetings (Google Meet, Microsoft Teams). Critical action items and verbal commitments are frequently forgotten, deadlines are left ambiguous, and meeting minutes require tedious manual synthesis. Existing commercial solutions often lock data behind expensive proprietary subscriptions and transmit sensitive meeting audio to closed third-party clouds, violating enterprise and organizational privacy standards.
- **Intended Users**: Engineers, engineering managers, product teams, distributed remote organizations, and open-source contributors who require automated meeting intelligence using 100% open-weights models and local/self-hosted infrastructure.

### Key Features
1. **Multi-Platform Meeting Support**: Seamlessly captures live captions and speech on **Google Meet** and **Microsoft Teams** via non-intrusive DOM MutationObservers with speaker attribution and debounce buffering.
2. **Open-Source Meeting Summarization**: Powered by **Gemma** (Gemma 2 9B/27B or Gemma 3), synthesizing executive overviews, key discussion topics, and finalized decisions.
3. **Per-Person Action Items (To-Do List)**: Extracts commitments, assignments, and follow-ups mapped to each meeting participant into an interactive to-do list.
4. **Calendar Reminders & Missing Deadline Resolution**: Automatically schedules Google Calendar reminder events ($T-24\text{h}$ and $T-2\text{h}$ alerts). If a participant mentions a task without a deadline, the agent prompts the user in the extension UI and automatically dispatches polite follow-up email nudges via Gmail if unset.
5. **Interactive Review & Task Completion**: Built-in Chrome Side Panel allows users to review tasks, filter by assignee, tick off completed items, reschedule, or cancel them.
6. **Persistent Reminders**: Background alarms (`chrome.alarms`) and Chrome desktop notifications persist alerts until a task is completed, cancelled, or rescheduled.
7. **Manual Task Creation**: Users can create ad-hoc action items with due dates and automatic Google Calendar synchronization.
8. **User Ownership with Google Drive**: Authenticates via Gmail (`chrome.identity` + OAuth2 PKCE); all meeting notes, summaries, and action checklists are automatically saved into `/MeetingMind/` on the user's personal Google Drive.

---

## Technical Stack

List of primary frameworks, languages, models, and external services used:
- **Language & Runtime**: TypeScript / JavaScript (Node.js 20+), Python 3.10+
- **Agent Framework & Protocols**: Google Agent Development Kit (ADK) patterns, Agent-to-Agent (A2A) event bus, Model Context Protocol (MCP)
- **Frontend / Extension Architecture**: Chrome Extension Manifest V3, React 18, Tailwind CSS, Lucide Icons, Vite
- **Models**: Gemma 2 (9B / 27B) or Gemma 3 running via Ollama, vLLM, or local OpenAI-compatible endpoints; built-in heuristic fallback engine for offline reliability
- **External APIs & Tools**: Google Workspace APIs (Google Drive REST API v3, Google Calendar API v3, Gmail REST API v1), SQLite (`meetingmind.db`)

### Dependency Manifests & Environment Templates
- **[`package.json`](package.json)**: Declares all extension and frontend packages (`react`, `react-dom`, `lucide-react`, `tailwindcss`, `vite`, `typescript`).
- **[`requirements.txt`](requirements.txt)** & **[`pyproject.toml`](pyproject.toml)**: Declares all backend multi-agent and MCP dependencies (`fastapi`, `uvicorn`, `pydantic`, `httpx`, `mcp`, `google-api-python-client`, `pytest`).
- **[`.env.example`](.env.example)**: Provides placeholder values for all required and optional configuration keys (Ollama endpoint, Gemma model tag, Google OAuth Client ID/Secret, server port).

---

## Architecture & Data Flow

```
+-----------------------------------------------------------------------------------------+
|                                CHROME BROWSER EXTENSION                                 |
|                                                                                         |
|   +------------------------------------+     +--------------------------------------+   |
|   |         CONTENT SCRIPTS            |     |            SIDE PANEL UI             |   |
|   |  - Google Meet Caption Observer    |     |  - Live Diarized Captions Feed       |   |
|   |  - MS Teams Caption Observer       |     |  - Gemma Executive Summary View      |   |
|   |  - Floating Status Overlay Badge   |     |  - Per-Person Action Items Checklist |   |
|   +-----------------+------------------+     |  - Missing Deadline Resolution Modal |   |
|                     |                        |  - Manual Task Creation Form         |   |
|                     | Transcript Stream      +------------------+-------------------+   |
|                     v                                           | User Actions          |
|   +-------------------------------------------------------------+-------------------+   |
|   |                      BACKGROUND SERVICE WORKER (MV3)                            |   |
|   |  - Google OAuth2 PKCE Manager (chrome.identity: Drive, Calendar, Gmail)         |   |
|   |  - Persistent Alarms & Nudge Daemon (chrome.alarms)                             |   |
|   |  - Local Offline-First Storage Cache (chrome.storage.local)                     |   |
|   +---------------------------------+-----------------------------------------------+   |
+-------------------------------------|---------------------------------------------------+
                                      | A2A Event Bus (JSON-RPC / REST)
                                      v
+-----------------------------------------------------------------------------------------+
|                              ADK & A2A MULTI-AGENT ENGINE                               |
|                                                                                         |
|   +-----------------------+     +-----------------------+     +---------------------+   |
|   |   Ingestion Agent     | --> |   Summarizer Agent    | --> | Action Item Agent   |   |
|   | (Cleanse/Diarization) |     |  (Gemma 2 / Gemma 3)  |     | (JSON Schema / NER) |   |
|   +-----------------------+     +-----------------------+     +----------+----------+   |
|                                                                          |              |
|                                                                          v              |
|   +-----------------------+                                   +---------------------+   |
|   |  Nudge & Email Agent  | <-------------------------------- | Scheduler Agent     |   |
|   | (Unset Deadline/Age)  |                                   | (Calendar / Prompts)|   |
|   +-----------+-----------+                                   +----------+----------+   |
+---------------|----------------------------------------------------------|--------------+
                |                                                          |
                +----------------------------+-----------------------------+
                                             | MCP Standard Tool Calls
                                             v
+-----------------------------------------------------------------------------------------+
|                               MODEL CONTEXT PROTOCOL (MCP)                              |
|                                                                                         |
|      +---------------------+   +-----------------------+   +---------------------+      |
|      |  Drive MCP Server   |   |  Calendar MCP Server  |   |   Gmail MCP Server  |      |
|      | - /MeetingMind/ Doc |   | - Create Event/Alarm  |   | - Send Nudge Email  |      |
|      +----------+----------+   +-----------+-----------+   +----------+----------+      |
|                 |                          |                          |                 |
|                 v                          v                          v                 |
|        [ Google Drive API ]       [ Google Calendar API ]       [ Gmail REST API ]      |
+-----------------------------------------------------------------------------------------+
```

---

## Prerequisites

Before running this project, ensure you have:
- **Node.js**: `v18.0.0+` or `v20.0.0+` (tested with Node 20.20.0) and `npm`
- **Python**: `3.10+` and `pip`
- **Ollama** (Optional for local inference, or use remote vLLM):
  ```bash
  ollama pull gemma2:9b
  ```
- **Google Cloud Console Project**:
  - Enable **Google Drive API**, **Google Calendar API**, and **Gmail API**.
  - Configure the OAuth consent screen with scopes:
    - `https://www.googleapis.com/auth/userinfo.email`
    - `https://www.googleapis.com/auth/userinfo.profile`
    - `https://www.googleapis.com/auth/drive.file`
    - `https://www.googleapis.com/auth/calendar.events`
    - `https://www.googleapis.com/auth/gmail.send`
  - Create an OAuth 2.0 Client ID (Application type: *Chrome Extension* or *Web Application*).

---

## Installation & Setup

### 1. Clone & Navigate to Project Directory
```bash
cd agents/meeting-task-agent
```

### 2. Set Up the Python Agent Backend
```bash
cd backend

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install backend dependencies
pip install -r requirements.txt

# Copy environment template
cp ../.env.example .env
```

### 3. Build the Chrome Extension
```bash
cd agents/meeting-task-agent

# Install frontend dependencies
npm install

# Compile TypeScript and bundle with Vite into dist/
npm run build
```

### 4. Load the Extension in Google Chrome
1. Open Google Chrome and enter `chrome://extensions/` in the URL bar.
2. Toggle **Developer mode** on (top-right corner).
3. Click **Load unpacked** (top-left).
4. Select the directory: `agents/meeting-task-agent/dist`.
5. Pin **MeetingMind AI** to your Chrome toolbar.

---

## Configuration & Environment Variables

Edit `backend/.env` (or `agents/meeting-task-agent/.env.example`):

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Endpoint for Ollama open-source LLM runtime |
| `GEMMA_MODEL` | No | `gemma2:9b` | Model identifier tag (e.g. `gemma2:9b`, `gemma:2b`, `gemma2:27b`) |
| `VLLM_BASE_URL` | No | *None* | Optional remote vLLM / OpenAI-compatible endpoint |
| `VLLM_API_KEY` | No | *None* | Optional API key for remote vLLM endpoint |
| `GOOGLE_CLIENT_ID` | Yes | *None* | Google OAuth 2.0 Client ID for Workspace authentication |
| `GOOGLE_CLIENT_SECRET` | Yes | *None* | Google OAuth 2.0 Client Secret |
| `HOST` | No | `0.0.0.0` | FastAPI server host binding |
| `PORT` | No | `8000` | FastAPI server listening port |
| `DB_PATH` | No | `./meetingmind.db` | Local SQLite database file for task persistence |
| `NUDGE_GRACE_HOURS` | No | `2` | Hours to wait before sending an email nudge for missing deadlines |

---

## How to Run

### Step 1: Start Ollama (or local LLM server)
```bash
ollama run gemma2:9b
```
*(If Ollama is not installed or running, the agent automatically utilizes its built-in rule and heuristic fallback engine).*

### Step 2: Start the MeetingMind Agent Backend
```bash
cd agents/meeting-task-agent/backend
source .venv/bin/activate
python main.py
```
The FastAPI backend will start on `http://localhost:8000`.

### Step 3: Launch Google Meet or Teams
1. Open a Google Meet (`https://meet.google.com`) or Teams (`https://teams.microsoft.com`) call.
2. Ensure closed captions are turned on (`CC` button in Meet).
3. The floating pill **MeetingMind AI Active** appears in the bottom-left corner.
4. Click the pill or the extension icon to open the **MeetingMind Side Panel**.
5. Click **Sign in with Gmail** to grant permission to sync notes with Google Drive and Calendar.
6. Click **Summarise** to generate the executive brief, or click **Extract Action Items** to populate your interactive to-do list.

---

## Example Input & Output

### Example Input: Raw Speech Stream (Google Meet)
```
Sarah Chen: "Good morning team. Let's review the Q3 infrastructure migration."
Alex Rivera: "I will run the PostgreSQL benchmark tests and share the performance report by Friday at 5 PM."
David Kim: "I will review the SOC2 audit findings and patch the authorization headers."
Sarah Chen: "Do you have an ETA for that David?"
David Kim: "I need to check the team bandwidth first, so no fixed date yet."
Sarah Chen: "Alright, let's track it. I will schedule the demo with executive stakeholders for next Tuesday 10 AM."
```

### Example Output 1: Gemma Meeting Summary
```json
{
  "overview": "The team aligned on Q3 infrastructure milestones, prioritizing database benchmarks, SOC2 security compliance, and stakeholder demonstrations.",
  "key_points": [
    "PostgreSQL performance benchmarking scheduled for completion this week.",
    "SOC2 security audit findings require authorization header patches.",
    "Executive demo scheduled for next Tuesday."
  ],
  "decisions": [
    "Approved PostgreSQL benchmark plan and team task ownership."
  ]
}
```

### Example Output 2: Extracted Action Items To-Do List
```json
{
  "action_items": [
    {
      "owner": "Alex Rivera",
      "task": "Run PostgreSQL benchmark tests and share performance report",
      "deadline": "2026-10-30T17:00:00Z",
      "priority": "high",
      "status": "pending"
    },
    {
      "owner": "David Kim",
      "task": "Review SOC2 audit findings and patch authorization headers",
      "deadline": null,
      "priority": "medium",
      "status": "pending"
    },
    {
      "owner": "Sarah Chen",
      "task": "Schedule executive stakeholder demo",
      "deadline": "2026-11-03T10:00:00Z",
      "priority": "medium",
      "status": "pending"
    }
  ]
}
```

### Example Output 3: Automated Email Nudge (Missing Deadline)
```
Subject: [Action Required] Set deadline for: Review SOC2 audit findings and patch...
To: david.kim@company.com

Hi David Kim,

During the meeting 'Q3 Infrastructure Sync', you were assigned the following action item:
"Review SOC2 audit findings and patch authorization headers"

A deadline has not yet been specified. Please open MeetingMind or reply with your target completion date so calendar reminders can be scheduled.

Best regards,
MeetingMind AI Agent
```

---

## How to Test

### 1. Run Frontend Extension Unit Tests
Tests caption chunking, speaker attribution, debounce logic, and task state changes:
```bash
cd agents/meeting-task-agent
npm test
```

### 2. Run Backend Multi-Agent & MCP Unit Tests
Tests the Ingestion Agent, Gemma prompt handling, Action Extractor Agent, Scheduler Agent, and SQLite Task Store:
```bash
cd agents/meeting-task-agent/backend
source .venv/bin/activate
python -m unittest ../tests/backend/test_agents.py
```

### 3. Run the End-to-End Simulation Script
Simulates a multi-speaker meeting with caption ingestion, Gemma summarization, action item extraction, calendar evaluation, email nudge drafting, and Google Drive Markdown generation:
```bash
cd agents/meeting-task-agent
backend/.venv/bin/python tests/simulate_meeting.py
```

For complete testing flows, see [`TESTING.md`](TESTING.md).

---

## Known Limitations

- **Browser Closed Captions Dependency**: Relies on browser-rendered closed captions or transcripts in Google Meet and Microsoft Teams. If captions are toggled off by all users in the meeting, audio capture fallback via tab streaming requires explicit user permission.
- **Meeting Audio Quality & Background Noise**: Speech-to-text accuracy in the host platform directly influences diarization quality.
- **Local Gemma Hardware Requirements**: Running Gemma 2 9B locally requires ~8GB of VRAM (or ~6GB with 4-bit quantization). On lower-spec machines, Gemma 2 2B or CPU inference is recommended.
- **Google Cloud Quotas**: Free-tier Google Workspace APIs enforce daily request quotas (e.g. 250 quota units per day for Gmail send operations).

---

## Security & Privacy Considerations

- **Secrets Handling**: OAuth tokens are stored in `chrome.storage.local` with strict origin separation. No user secrets, refresh tokens, or passwords are hardcoded or tracked in Git.
- **Data Privacy & Data Sovereignty**: Transcripts are processed through your configured local or self-hosted Gemma model instance. No audio or text is transmitted to third-party proprietary LLM providers.
- **Google Drive Least-Privilege Scope**: Uses `https://www.googleapis.com/auth/drive.file`. MeetingMind can only read and write files it created itself in `/MeetingMind/`; it has zero access to any pre-existing user files on Google Drive.
- **Safe Execution**: The agent does not execute arbitrary shell commands or unsanctioned network endpoints.

---

## Future Improvements

- [ ] Add direct on-device Gemma inference via WebGPU and MediaPipe inside the Chrome extension without requiring a Python backend.
- [ ] Support Zoom Web Client caption DOM observer.
- [ ] Add bi-directional sync with Slack and Linear for automatic issue creation from action items.
- [ ] Add audio diarization via open-source Whisper for recorded audio uploads.

---

## License

This project is contributed under the repository's open-source license.
