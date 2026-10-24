# MeetingMind AI Agent — Architectural Design & Step-by-Step Execution Plan

> **Project Name**: MeetingMind Agent (`meeting-task-agent`)  
> **Type**: Manifest V3 Chrome Extension + ADK & A2A Open-Source Agent Backend  
> **Status**: Proposed Implementation Plan (Awaiting Confirmation)

---

## 1. Executive Summary & Objective

**MeetingMind** is an open-source, privacy-first Chrome Extension and multi-agent system designed to join or observe virtual meetings (Google Meet, Microsoft Teams, etc.), capture real-time transcripts, generate structured meeting summaries, extract per-person action items into an interactive to-do list, and automate schedule reminders and email follow-ups.

### Key Highlights
- **100% Open-Source LLM Architecture**: Powered by **Gemma** (Gemma 2 9B/27B or Gemma 3 via Ollama/vLLM or local on-device inference via WebGPU/Chrome Built-in AI).
- **Standardized Tool Context via MCP**: Implements Model Context Protocol (MCP) servers for Google Workspace (Drive, Calendar, Gmail).
- **Multi-Agent Collaboration via ADK & A2A**: Built with Google's **Agent Development Kit (ADK)** and the **Agent-to-Agent (A2A)** protocol for specialized sub-agents (Ingestion, Summarization, Scheduling, and Email Nudging).
- **User Ownership & Storage**: Seamless Gmail authentication (`chrome.identity` + OAuth2); all meeting notes, summaries, and action items are stored directly in the user's personal Google Drive.
- **Zero Premature Execution**: This document outlines the exhaustive step-by-step implementation plan. **No implementation code will be written until this plan is formally approved.**

---

## 2. Requirements & Feature Traceability Matrix

| # | Feature / Requirement | Technical Approach | Components Involved |
|---|---|---|---|
| **1** | Google Meet, Microsoft Teams & Web Meeting Support | Content scripts with MutationObservers for live captions + fallback tab audio streaming. | `content-scripts/meet.ts`, `content-scripts/teams.ts` |
| **2** | Meeting Summarization | Gemma 2 / Gemma 3 structured prompt pipeline generating executive briefs, topics discussed, and key decisions. | `agents/summarizer_agent.py`, Gemma Model Runner |
| **3** | Action Items extraction per person as To-Do list | Speaker diarization & NER mapping to participants; structured JSON schema output (`owner`, `task`, `deadline`, `priority`). | `agents/action_item_agent.py`, Schema Validator |
| **4** | Calendar reminders & missing deadline query loop | Google Calendar MCP tool schedules reminders. Missing deadline triggers interactive extension UI prompt and scheduled email nudge. | `agents/calendar_scheduler_agent.py`, `Google Calendar MCP` |
| **5** | Interactive To-Do list & tick off completed tasks | Side Panel UI with real-time bidirectional sync to Google Drive & local indexed database. | `sidepanel/src/components/TodoList.tsx`, Drive Sync |
| **6** | Persistent reminders until completed / cancelled / rescheduled | Chrome alarms + background service worker + Calendar alerts repeating until task status updates. | `background/reminder_daemon.ts`, `chrome.alarms` |
| **7** | Manual task creation with reminder configuration | Side panel "Add Task" modal with deadline picker, owner assignment, and automatic Calendar/Email hook. | `sidepanel/src/components/NewTaskModal.tsx` |
| **8** | Open-source Stack (Gemma, MCP, ADK, A2A) | Google ADK multi-agent orchestration, MCP client/server architecture, A2A event bus, Gemma inference backend. | `backend/adk_engine/`, `mcp_servers/` |
| **9** | Gmail Authentication & Google Drive persistence | Chrome Identity API (OAuth2 PKCE); Drive REST API creates organized notes folder (`/MeetingMind/`). | `auth/google_auth.ts`, `mcp_servers/drive_server.py` |

---

## 3. High-Level System Architecture

```
+--------------------------------------------------------------------------------------------------+
|                                    CHROME BROWSER EXTENSION                                      |
|                                                                                                  |
|   +------------------------------------+          +------------------------------------------+   |
|   |          CONTENT SCRIPTS           |          |            SIDE PANEL UI                 |   |
|   |  - Google Meet Caption Observer    |          |  - Live Transcript & Meeting Status      |   |
|   |  - MS Teams Caption Observer       |          |  - Real-time Executive Summary View      |   |
|   |  - Fallback Web Audio / Tab Capture|          |  - Interactive To-Do List (Tick/Edit)    |   |
|   +-----------------+------------------+          |  - Manual Task Addition & Deadline Input |   |
|                     | Transcript Stream           +--------------------+---------------------+   |
|                     v                                                  | User Actions            |
|   +--------------------------------------------------------------------+---------------------+   |
|   |                           BACKGROUND SERVICE WORKER (MV3)                                |   |
|   |  - OAuth 2.0 Auth Manager (chrome.identity: Gmail, Drive, Calendar scopes)               |   |
|   |  - chrome.alarms (Persistent Task Nudge & Reminder Daemon)                               |   |
|   |  - Local Storage Cache (chrome.storage.local / IndexedDB)                                |   |
|   +------------------------------------+-----------------------------------------------------+   |
+----------------------------------------|---------------------------------------------------------+
                                         | Secure REST / WebSocket / JSON-RPC
                                         v
+--------------------------------------------------------------------------------------------------+
|                                 ADK & A2A MULTI-AGENT BACKEND                                    |
|                                                                                                  |
|   +------------------------------------------------------------------------------------------+   |
|   |                         A2A (Agent-to-Agent) ORCHESTRATOR BUS                            |   |
|   |                                                                                          |   |
|   |   +-----------------------+     +-----------------------+     +-----------------------+  |   |
|   |   |   Ingestion Agent     | --> |   Summarizer Agent    | --> |  Action Item Agent    |  |   |
|   |   | (Diarization/Cleanse) |     |   (Gemma 2 / Gemma 3) |     |  (Gemma JSON Schema)  |  |   |
|   |   +-----------------------+     +-----------------------+     +-----------+-----------+  |   |
|   |                                                                           |              |   |
|   |                                                                           v              |   |
|   |   +-----------------------+                                   +-----------------------+  |   |
|   |   |  Nudge & Email Agent  | <-------------------------------- | Scheduler & Cal Agent |  |   |
|   |   |  (Missing Deadline/   |                                   | (Auto-schedule / Ask  |  |   |
|   |   |   Overdue Monitor)    |                                   |  user for deadlines)  |  |   |
|   |   +-----------+-----------+                                   +-----------+-----------+  |   |
|   +---------------|-----------------------------------------------------------|--------------+   |
|                   |                                                           |                  |
|                   |                      MCP PROTOCOL CLIENT                  |                  |
|                   +-----------------------------+-----------------------------+                  |
+-------------------------------------------------|------------------------------------------------+
                                                  | Tool Calls (MCP Standard)
                                                  v
+--------------------------------------------------------------------------------------------------+
|                                    MCP SERVERS & GOOGLE APIS                                     |
|                                                                                                  |
|   +-----------------------+     +-----------------------+     +-----------------------+          |
|   |   Drive MCP Server    |     |  Calendar MCP Server  |     |   Gmail MCP Server    |          |
|   |  - Create Meeting Doc |     |  - Create Event/Alarm |     |  - Send Nudge Emails  |          |
|   |  - Update Action Items|     |  - Reschedule / Delete|     |  - Follow-up Triggers |          |
|   +-----------------------+     +-----------------------+     +-----------------------+          |
|               |                             |                             |                      |
|               v                             v                             v                      |
|      [ Google Drive API ]          [ Google Calendar API ]         [ Gmail REST API ]            |
+--------------------------------------------------------------------------------------------------+
```

---

## 4. Multi-Agent Design (ADK & A2A)

The backend agent workflow is built using the **Google Agent Development Kit (ADK)** and coordinates specialized tasks via the **Agent-to-Agent (A2A)** pattern:

### Agent 1: Ingestion & Transcript Normalizer Agent
- **Role**: Ingests raw chunks emitted by the Chrome Extension content script.
- **Function**: Deduplicates overlapping captions, attributes speech to verified participant identities, normalizes timestamps, and produces a coherent, chronologically ordered meeting transcript.

### Agent 2: Meeting Summarizer Agent
- **Role**: Core comprehension and synthesis.
- **Model**: Gemma 2 9B/27B (or Gemma 3) instructed with a specialized meeting summarization system prompt.
- **Outputs**:
  - Executive TL;DR (3–5 bullet points).
  - Detailed thematic breakdown with speaker citations.
  - Final decisions agreed upon by stakeholders.

### Agent 3: Action Item & Responsibility Extraction Agent
- **Role**: Action orientation and entity extraction.
- **Model**: Gemma with constrained structured decoding (JSON Schema).
- **Logic**:
  - Identifies commitments, assignments, requests, and delegated tasks.
  - Extracts `{ task_id, owner_name, owner_email, task_description, deadline, confidence }`.
  - Distinguishes explicit deadlines ("by Friday 5 PM") from ambiguous ones ("next week", "soon", or omitted).

### Agent 4: Calendar & Task Scheduler Agent (via MCP)
- **Role**: Scheduling and deadline resolution.
- **Logic**:
  - If deadline is explicitly present: Calls `google_calendar.create_event_reminder` tool with calculated notification alerts.
  - If deadline is `null` or ambiguous: Emits an `AWAITING_USER_DEADLINE` event to the Chrome Extension side panel to prompt the user.

### Agent 5: Nudge & Follow-up Agent (via MCP & A2A)
- **Role**: Task completion watchman and communication assistant.
- **Logic**:
  - Monitors tasks stored in the Google Drive / Local database.
  - Checks if deadlines remain unset for >2 hours after meeting conclusion. If unset, triggers a draft/sent nudge email to the meeting organizer or task owner via `gmail.send_nudge`.
  - Evaluates unfinished tasks against approaching deadlines and dispatches reminders until the task is marked as `completed`, `cancelled`, or `rescheduled`.

---

## 5. Model Context Protocol (MCP) Server Specifications

MCP standardizes how the Gemma agents access Google Workspace tools. We define three MCP servers (or one modular Workspace MCP server):

### 1. `DriveMCPServer`
- **`save_meeting_summary(title, markdown_content, metadata)`**:
  - Checks/creates `/MeetingMind/Meetings/` folder in user's root Drive.
  - Creates a formatted Google Doc or Markdown file.
- **`update_action_items(doc_id, items_list)`**:
  - Appends or updates the checklist state in the Drive document.

### 2. `CalendarMCPServer`
- **`create_task_reminder(title, description, start_time, end_time, attendees)`**:
  - Creates a Google Calendar event / reminder with pop-up notification at `T-24h` and `T-2h`.
- **`update_task_reminder(event_id, new_deadline, status)`**:
  - Reschedules or deletes the calendar event when marked completed/cancelled.

### 3. `GmailMCPServer`
- **`send_nudge_email(to_email, task_description, meeting_title, reason)`**:
  - Generates a concise, polite follow-up nudge asking the owner for an ETA or reminding them of pending deliverables.

---

## 6. Chrome Extension Architecture (Manifest V3)

### Structure & Directory Layout
```
agents/meeting-task-agent/
├── README.md                          # Contributor and user documentation
├── .env.example                       # Template for API endpoints and client IDs
├── manifest.json                      # Chrome Extension MV3 Manifest
├── package.json                       # Extension & frontend dependencies
├── tsconfig.json                      # TypeScript configuration
├── src/
│   ├── background/
│   │   ├── index.ts                   # Service worker entrypoint
│   │   ├── auth.ts                    # Google OAuth2 PKCE & token management
│   │   ├── alarms.ts                  # Persistent reminder loops & notification triggers
│   │   └── a2a_client.ts              # Agent communication layer (REST / WebSocket)
│   ├── content/
│   │   ├── meet.ts                    # Google Meet DOM Caption Observer
│   │   ├── teams.ts                   # Microsoft Teams DOM Caption Observer
│   │   └── audio_capture.ts           # Fallback tabCapture / Web Audio stream
│   ├── sidepanel/
│   │   ├── index.html                 # Extension Side Panel host HTML
│   │   ├── main.tsx                   # React / UI root
│   │   ├── components/
│   │   │   ├── MeetingHeader.tsx      # Meeting status & live recording indicator
│   │   │   ├── SummaryTab.tsx         # Executive summary & key decisions
│   │   │   ├── TodoList.tsx           # Interactive to-do list with check/reschedule
│   │   │   ├── TodoItem.tsx           # Single task item with deadline badge & actions
│   │   │   ├── NewTaskModal.tsx       # Manual task entry modal
│   │   │   ├── DeadlinePrompt.tsx     # Popup prompt for tasks missing deadlines
│   │   │   └── DriveSyncStatus.tsx    # Google Drive sync badge and link
│   │   └── styles/
│   │       └── globals.css            # Tailwind / CSS styles
│   └── shared/
│       ├── types.ts                   # Shared TypeScript interfaces (Task, Meeting, etc.)
│       └── constants.ts               # Storage keys, endpoint URLs, scopes
├── backend/
│   ├── requirements.txt               # Python dependencies (ADK, mcp, vllm/ollama, fastapi)
│   ├── main.py                        # FastAPI server exposing A2A agent endpoints
│   ├── adk_engine/
│   │   ├── orchestrator.py            # A2A Multi-agent orchestrator
│   │   ├── agents/
│   │   │   ├── summarizer.py          # Gemma Summarization Agent
│   │   │   ├── action_extractor.py    # Gemma Action Item Extraction Agent
│   │   │   ├── scheduler.py           # Calendar & Deadline Agent
│   │   │   └── nudger.py              # Follow-up & Email Nudge Agent
│   │   └── prompts/
│   │       ├── summarization.py       # Gemma few-shot summarization prompt templates
│   │       └── action_extraction.py   # Gemma JSON-schema extraction templates
│   └── mcp_servers/
│       ├── workspace_mcp.py           # Google Workspace (Drive, Calendar, Gmail) MCP Tools
│       └── local_store_mcp.py         # Persistent SQLite/JSON storage MCP server
└── tests/
    ├── extension/                     # Unit tests for caption extractors & storage
    └── backend/                       # Unit tests for agents, Gemma prompts & MCP tools
```

---

## 7. Step-by-Step Implementation Roadmap

```
  Phase 0: Architecture & Protocol Specifications (CURRENT)
      │
      v
  Phase 1: Project Scaffolding & Dependencies Setup
      │
      v
  Phase 2: Chrome Extension - Captions & Live Ingestion (Meet & Teams)
      │
      v
  Phase 3: Authentication (Gmail/OAuth2) & Google Workspace MCP Setup
      │
      v
  Phase 4: Open-Source Gemma Model Engine & ADK Agent Pipeline
      │
      v
  Phase 5: Extension UI (Side Panel, Live Notes, Interactive To-Do)
      │
      v
  Phase 6: Deadline Clarification, Calendar Sync & Email Nudge Automation
      │
      v
  Phase 7: End-to-End Verification, Mock Meetings & Edge Case Hardening
      │
      v
  Phase 8: Documentation, Packaging & PR Submission to Repository
```

### Detailed Breakdown of Implementation Steps:

#### **Phase 1: Project Scaffolding & Setup**
1. Initialize repository directory `agents/meeting-task-agent`.
2. Configure `manifest.json` (Manifest V3) with required permissions:
   - `identity`, `storage`, `alarms`, `sidePanel`, `activeTab`, `scripting`.
   - Host permissions: `https://meet.google.com/*`, `https://teams.microsoft.com/*`, `https://www.googleapis.com/*`.
3. Set up frontend toolchain (Vite, TypeScript, Tailwind CSS, lucide-react).
4. Set up Python agent backend with Google ADK, FastAPI, and MCP SDK.

#### **Phase 2: Meeting Caption Ingestion Engine**
1. Implement `src/content/meet.ts`:
   - Identify Google Meet live caption containers (`[jsname="YSvyTc"]`, speaker labels `[class*="zs7s8d"]`).
   - MutationObserver streaming buffer with debounce logic to avoid partial sentence duplication.
2. Implement `src/content/teams.ts`:
   - Observe Microsoft Teams live captions and transcript panels (`.ui-chat__item`, `.closed-captions`).
3. Build communication channel (`chrome.runtime.sendMessage`) forwarding live text chunks to the background service worker.

#### **Phase 3: Google Workspace Authentication & MCP Integration**
1. Configure Google Cloud Console OAuth 2.0 Client ID for Chrome Extensions.
2. Implement `chrome.identity.getAuthToken` with scopes:
   - `https://www.googleapis.com/auth/drive.file`
   - `https://www.googleapis.com/auth/calendar.events`
   - `https://www.googleapis.com/auth/gmail.send`
   - `https://www.googleapis.com/auth/userinfo.email`
3. Implement `workspace_mcp.py` exposing standardized MCP tools for:
   - Drive: creating/updating Markdown and Doc files in `/MeetingMind/`.
   - Calendar: adding/updating reminder events.
   - Gmail: sending nudge messages.

#### **Phase 4: Gemma Model Engine & ADK Multi-Agent Core**
1. Configure Gemma inference provider:
   - Support for local Ollama (`ollama run gemma2:9b` or `gemma:2b`) and remote vLLM endpoints.
2. Implement ADK Agent Pipeline:
   - **Ingestion & Diarization Agent**: formats messy live captions into clean transcript segments.
   - **Summarizer Agent**: generates overview, discussions, decisions.
   - **Action Item Agent**: enforces JSON schema extraction:
     ```json
     {
       "action_items": [
         {
           "id": "uuid",
           "owner": "Alice Smith",
           "owner_email": "alice@example.com",
           "task": "Finalize Q3 infrastructure budget proposal",
           "deadline": "2026-10-30T17:00:00Z",
           "status": "pending"
         }
       ]
     }
     ```
3. Implement A2A event router routing tasks between agents and extension UI.

#### **Phase 5: Extension Side Panel & Interactive To-Do UI**
1. Build Side Panel application:
   - Header with active meeting title, recording toggle, Drive sync status.
   - Tab 1: **Summary & Transcript** (live updating notes, executive summary).
   - Tab 2: **Action Items & To-Do List**:
     - Filter by person / owner or "My Tasks".
     - Checkbox to tick off completed items.
     - Reschedule button (date picker) and cancel button.
   - Tab 3: **Manual Task Entry**:
     - Form allowing user to create custom tasks with title, owner, and deadline.

#### **Phase 6: Deadline Resolution, Calendar Reminders & Email Nudges**
1. **Interactive Deadline Dialog**:
   - If an action item has `deadline: null`, flag in Side Panel: *"Please set a deadline for [Task]"*.
2. **Calendar Sync**:
   - On confirmed deadline: automatically call `create_task_reminder` via Calendar MCP.
3. **Nudge & Follow-up Daemon**:
   - `chrome.alarms` fires every hour or at configurable intervals.
   - If task is incomplete and:
     - No deadline has been set after 2 hours: Dispatches an email nudge via Gmail API.
     - Deadline is approaching (24h / 2h): Sends desktop notification + email reminder.
   - Remains active and repeats until task is marked `completed`, `cancelled`, or `rescheduled`.

#### **Phase 7: Testing, Edge Cases & Verification**
1. Unit tests for caption parsers with mock Google Meet and Teams HTML streams.
2. Evaluation test cases for Gemma prompt outputs on sample meeting transcripts.
3. OAuth token refresh and offline storage fallback testing.
4. User cancellation and task reschedule flow tests.

#### **Phase 8: Documentation & Repository Contribution**
1. Complete `agents/meeting-task-agent/README.md` following repository template guidelines.
2. Provide `.env.example` with clear instructions on Google Cloud OAuth setup and Gemma backend configuration.
3. Create architecture diagrams and demo guide.

---

## 8. Data Privacy, Permissions & Security

- **Strict User Privacy**: Meeting audio/captions are processed strictly through the user's configured open-source Gemma endpoint (local or self-hosted). No data is shared with third-party LLM vendors.
- **Drive Least Privilege**: Utilizes `drive.file` scope—MeetingMind can only access files and folders it creates itself; it cannot inspect or read any pre-existing user files.
- **Local Persistence**: Offline-first via `chrome.storage.local` with encryption-at-rest for OAuth access tokens.

---

## 9. User Sign-off & Confirmation Gate

> [!IMPORTANT]
> **Awaiting User Review**: In accordance with the instructions, **no files, scripts, or extension code will be executed or modified until you review and confirm this plan**.
> 
> Please review the steps, technical choices (Gemma, ADK, A2A, MCP, Google OAuth, Chrome MV3), and let me know if you would like any modifications or if we should proceed with implementation!

