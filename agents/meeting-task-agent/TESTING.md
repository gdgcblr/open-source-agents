# MeetingMind AI — Complete Testing & Verification Guide

This guide provides step-by-step instructions to test and verify every component and feature of the **MeetingMind AI** system, covering automated unit tests, end-to-end multi-agent simulation, and manual verification inside Google Chrome.

---

## Testing Matrix Overview

| Level | Scope | Method | Time Required |
|---|---|---|---|
| **Level 1** | Automated Unit Tests (Frontend & Backend) | `npm test` & `python -m unittest` | ~5 seconds |
| **Level 2** | Full End-to-End Simulation Pipeline | `python tests/simulate_meeting.py` | ~10 seconds |
| **Level 3** | FastAPI Backend & MCP Server Verification | `curl` / `TestClient` | ~5 seconds |
| **Level 4** | Interactive Chrome Extension Testing | Unpacked Extension in Chrome | ~5 minutes |

---

## Step 1: Run Automated Unit Tests

### 1. Frontend & Extension Unit Tests
Tests caption deduplication, delta chunk calculation, speaker change detection, and action item state transitions.

```bash
cd agents/meeting-task-agent

# Run extension unit tests
npm test
```

**Expected Result:**
```
✔ Transcript deduplication and delta chunk calculation
✔ Speaker change detection
✔ Action item state transition lifecycle
ℹ tests 3, pass 3, fail 0
```

---

### 2. Backend Multi-Agent & MCP Unit Tests
Tests the Ingestion Agent, Gemma prompt handling, Action Extractor Agent, Scheduler Agent, and SQLite Task Store.

```bash
cd agents/meeting-task-agent/backend

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Run backend unit tests
python -m unittest ../tests/backend/test_agents.py
```

**Expected Result:**
```
....
----------------------------------------------------------------------
Ran 4 tests in 0.023s

OK
```

---

## Step 2: Run End-to-End Meeting Simulation

To test the entire multi-agent pipeline without needing to open a live browser or call, run the simulation script.

```bash
cd agents/meeting-task-agent
backend/.venv/bin/python tests/simulate_meeting.py
```

This script executes:
1. **Live transcript ingestion** with multiple speakers (Sarah, Alex, David).
2. **Gemma Summarizer Agent** generating an executive overview, key highlights, and decisions.
3. **Gemma Action Extractor Agent** extracting action items mapped to participants.
4. **Scheduler Agent** identifying missing deadlines (e.g. David Kim's unset security task).
5. **Nudge & Follow-up Agent** drafting personalized follow-up emails via the Gmail MCP tool.
6. **Drive MCP Tool** formatting the complete meeting notes and checklist for Google Drive.

**Expected Output:**
```
🎯 MeetingMind AI — End-to-End Meeting Simulation
...
✔ Diarized into 10 aggregated speaker segments.
--- Executive Summary ---
Overview: Discussion in 'Q3 Architecture & Planning Sync' focused on...
Key Decisions:
  ✓ Approved task ownership and scheduled upcoming milestones...
✔ Extracted 3 action items mapped to participants:
  1. [Alex Rivera] Run PostgreSQL benchmark tests...
  2. [David Kim] Review SOC2 audit findings... (Due: [NO DEADLINE])
[Draft Email to David Kim]
Subject: [Action Required] Set deadline for: Review SOC2 audit findings...
✔ Google Drive Markdown Preview generated.
🎉 SIMULATION SUCCESSFUL!
```

---

## Step 3: Start the Backend & Verify MCP Tools

### 1. (Optional) Start Ollama for Local Gemma Inference
If you have Ollama installed with Gemma:
```bash
ollama run gemma2:9b
```
*(Note: If Ollama is not running, MeetingMind's built-in intelligent fallback agent automatically takes over to ensure zero disruption).*

### 2. Start the FastAPI Agent Backend
```bash
cd agents/meeting-task-agent/backend
source .venv/bin/activate
python main.py
```
The server will start at `http://localhost:8000`.

### 3. Verify Health & MCP Tools
In a separate terminal:
```bash
# Verify health check
curl http://localhost:8000/api/health

# Verify MCP tools
curl http://localhost:8000/api/mcp/tools
```

**Expected Response:**
```json
{
  "tools": [
    {"name": "google_drive_save_meeting"},
    {"name": "google_calendar_create_reminder"},
    {"name": "google_gmail_send_nudge"}
  ]
}
```

---

## Step 4: Build & Load the Chrome Extension

### 1. Build the Extension Bundle
```bash
cd agents/meeting-task-agent
npm run build
```
This compiles TypeScript, bundles React and Tailwind CSS, and prepares the unpacked extension in `dist/`.

### 2. Load the Extension into Google Chrome
1. Open Google Chrome and enter `chrome://extensions/` in the URL bar.
2. Toggle **Developer mode** (top-right corner).
3. Click **Load unpacked** (top-left).
4. Select the folder:  
   `/home/arkadyuti/project/open-source-agents/agents/meeting-task-agent/dist`
5. You will see **MeetingMind AI — Meeting Summarizer & Action Items** appear in your extensions list.
6. Pin **MeetingMind AI** to your Chrome toolbar for easy access.

---

## Step 5: Test Features in Google Meet & Microsoft Teams

### 1. Testing Live Caption Ingestion (Feature 1)
1. Start or join a meeting on **Google Meet** (`https://meet.google.com`) or **Microsoft Teams** (`https://teams.microsoft.com`).
2. Turn **ON** closed captions in the meeting (in Google Meet: click the `CC` button on the bottom bar).
3. Verify that the floating pill **MeetingMind AI Active** appears in the bottom-left corner of the meeting window.
4. Speak or simulate conversation. Notice the subtitle text appearing on screen.
5. Click the floating badge or the toolbar icon to open the **MeetingMind Side Panel**.

---

### 2. Testing Meeting Summarization (Feature 2)
1. In the Side Panel, navigate to the **Summary** tab.
2. Confirm that the line count shows: `X transcript lines captured`.
3. Click the **Summarise** button.
4. **Verification**:
   - Executive Overview card appears.
   - Key Discussion Points bullet points appear.
   - Decisions Made section appears with checkmarks.
   - Click **Live Transcript** accordion to inspect individual speaker segments with timestamps.

---

### 3. Testing Action Item Extraction as To-Do List (Feature 3)
1. In the Side Panel, navigate to the **Action Items** tab.
2. Click **Extract Action Items**.
3. **Verification**:
   - Action items appear grouped by participant.
   - Filter pills allow filtering by **All Owners**, or individual participants (e.g. *Sarah*, *Alex*).
   - Filter buttons allow toggling **All**, **Pending**, and **Done**.

---

### 4. Testing Deadline Prompts & Calendar Reminders (Feature 4)
1. For any action item that does not have an explicit deadline in speech:
   - Notice the amber alert banner: `⚠️ X tasks missing a deadline`.
   - Click the orange **Set Deadline** button.
2. In the popup modal:
   - Click one of the quick presets: **Tomorrow 9 AM**, **Fri 5 PM**, or **Next Mon**.
   - Or pick a custom date & time from the picker.
   - Click **Confirm & Sync**.
3. **Verification**:
   - The task card updates with the scheduled deadline date badge.
   - A Google Calendar link icon appears next to the task.
   - If signed in with Gmail, the reminder event is created in Google Calendar with $T-24\text{h}$ and $T-2\text{h}$ alerts.
   - If a deadline remains unset beyond the grace period, the **Nudge Agent** automatically drafts and dispatches a reminder email via Gmail.

---

### 5. Review & Tick Off Completed Tasks (Feature 5)
1. Click the circular checkbox on any pending action item card.
2. **Verification**:
   - The checkbox turns green with a checkmark (`CheckCircle2`).
   - The task title is struck through.
   - The pending counter in the header tab decrements.
   - The item moves to the **Done** tab.
   - Clicking again toggles it back to **Pending**.

---

### 6. Persistent Reminders & Badge Alerts (Feature 6)
1. Leave one or more tasks in `pending` status.
2. Observe the extension icon in Chrome's toolbar:
   - A red badge counter displays the exact number of pending items.
3. When deadlines approach (within 24 hours), Chrome creates high-priority desktop notifications:
   `MeetingMind Reminder: Task due soon - "[Task Title]" for [Owner]`.
4. Notifications and badge remain active until the task is marked **completed**, **cancelled**, or **rescheduled**.

---

### 7. Adding Manual Tasks with Reminders (Feature 7)
1. In the Side Panel, click the **+ Add Task** button.
2. Fill in the modal:
   - **Task Description**: `Prepare client presentation slides`
   - **Assignee / Owner**: `Me`
   - **Priority**: `High`
   - **Deadline**: Pick a future date/time.
3. Click **Save Action Item**.
4. **Verification**:
   - The new task appears immediately in your to-do list.
   - The calendar reminder is scheduled.

---

### 8. Google Drive Sync & Gmail Sign-In
1. In the top-right of the Side Panel, click **Sign in with Gmail**.
2. Chrome will launch the OAuth consent window asking for Drive, Calendar, and Gmail permissions.
3. Once approved, your avatar and email appear in the header.
4. Click **Sync to Drive** (cloud icon).
5. **Verification**:
   - The icon turns into a green `Drive` link.
   - Clicking it opens `/MeetingMind/<Meeting_Name>_Notes.md` in Google Drive containing the complete summary, action items checklist (`[x]`), and diarized transcript.

---

## Summary of Test Commands

```bash
# 1. Run all unit tests
cd agents/meeting-task-agent
npm test
backend/.venv/bin/python -m unittest tests/backend/test_agents.py

# 2. Run end-to-end multi-agent meeting simulation
backend/.venv/bin/python tests/simulate_meeting.py

# 3. Start backend agent server
cd backend && source .venv/bin/activate && python main.py
```

