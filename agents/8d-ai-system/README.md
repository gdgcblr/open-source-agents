# 8D AI System — Root Cause Analysis & Corrective Action Platform

An AI-assisted web application that guides quality engineers through the full **8 Disciplines (8D) problem-solving methodology** used in manufacturing. The AI generates structured suggestions for every step; humans review, edit, and approve each one. Every action is recorded in an immutable audit trail.

---

## What Problem Does This Solve?

In manufacturing, when a quality defect is found (a leaking gasket, a surface finish failure, a dimensional non-conformance), teams must follow the **8D process** — a structured, 8-step methodology to find the root cause and prevent recurrence. This process is usually done manually in spreadsheets or paper forms, which is:

- Slow to start (team doesn't know where to begin)
- Inconsistent across cases and engineers
- Hard to track across departments
- Missing the institutional knowledge from past cases

This system replaces that with an AI-guided, database-backed workflow where the AI does the initial heavy lifting and engineers stay in control.

---

## The 8D Methodology

| Step | Name | What It Captures |
|------|------|-----------------|
| **D1** | Team Formation | Who is on the problem-solving team and why |
| **D2** | Problem Description | What, when, where, who, how many — structured 5W1H |
| **D3** | Containment Actions | Immediate actions to stop the bleeding (stock holds, customer notification) |
| **D4** | Root Cause Analysis | Fishbone (Ishikawa) diagram + 5-Why drill-down → identified root cause |
| **D5** | Root Cause Verification | How to prove the root cause is real (test methods, evidence) |
| **D6** | Corrective Actions | Permanent fixes with owners and target dates |
| **D7** | Preventive Actions | System/process changes so it can never happen again |
| **D8** | Recognition & Closure | Executive summary, key learnings, team acknowledgment |

---

## Live Demo Flow

```
Engineer opens app → Clicks "New 8D Case"
   → Fills in: Problem Title, Plant, Product, Reported By, Priority
   → Clicks "Create 8D Case & Start AI Analysis"

System creates the case → Redirects to Case Detail page

For each D-step (D1 through D8):
   → Engineer clicks "Generate with AI"
   → AI produces structured JSON suggestion
   → Engineer reviews the output, edits any field inline
   → Clicks "Approve & Continue"
   → Case advances to next step automatically

After D8 is approved → Case status becomes CLOSED
```

---

## Architecture Overview

```
Browser (React 19 / Next.js App Router)
    │
    ├── / ─────────────────── Dashboard (stats, pipeline, case list)
    ├── /cases/new ─────────── New case form
    └── /cases/[id] ─────────── Case detail (8D stepper)
             │
             ▼
    Next.js API Routes (server-side)
             │
    ┌────────┴────────────────────────────────┐
    │                                         │
    ▼                                         ▼
Prisma ORM                        LLM (OpenAI-compatible)
(better-sqlite3)                  e.g. GPT-4.1-mini, local model
    │                                         │
    ▼                                         │
SQLite (dev.db)          ◄───────────────────┘
(Cases, DSteps,          AI suggestions saved back to DB
 AuditLogs)
```

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Framework | Next.js (App Router, Turbopack) | 16.4.3 |
| UI | React | 19.3.0 |
| Language | TypeScript | 5.x |
| Styling | Tailwind CSS | v4 |
| Icons | Lucide React | 1.x |
| ORM | Prisma | 7.x |
| Database | SQLite via better-sqlite3 | — |
| AI | OpenAI-compatible REST API | configurable |

---

## Project Structure

```
8d-ai-system/
│
├── app/                          # Next.js App Router pages & API
│   ├── layout.tsx                # Root HTML layout, global metadata
│   ├── page.tsx                  # Dashboard — stats, pipeline, case table
│   ├── globals.css               # Tailwind v4 import + base styles
│   │
│   ├── cases/
│   │   ├── new/page.tsx          # New case creation form
│   │   └── [id]/page.tsx         # Case detail — 8D stepper (main UI)
│   │
│   └── api/
│       ├── cases/
│       │   ├── route.ts          # GET /api/cases, POST /api/cases
│       │   └── [id]/
│       │       ├── route.ts      # GET /api/cases/:id, PATCH /api/cases/:id
│       │       └── steps/
│       │           └── route.ts  # POST (save/edit step), PUT (approve step)
│       └── ai/
│           ├── suggest/route.ts  # POST — AI generates a D-step suggestion
│           └── similar/route.ts  # POST — find similar closed cases
│
├── components/
│   └── FishboneDiagram.tsx       # SVG Ishikawa diagram renderer
│
├── lib/
│   ├── db.ts                     # Prisma client singleton (SQLite adapter)
│   └── gemini.ts                 # LLM client (OpenAI-compatible fetch wrapper)
│
├── prisma/
│   ├── schema.prisma             # Database models: Case, DStep, AuditLog
│   ├── seed.ts                   # Sample data (2 closed cases with full steps)
│   └── dev.db                    # SQLite database file (auto-created)
│
└── prisma7.config.ts             # Prisma 7 driver adapter config
```

---

## Database Models

### `Case`
The top-level record for a quality problem.

| Field | Type | Description |
|-------|------|-------------|
| `id` | String (cuid) | Unique identifier |
| `title` | String | Problem description, e.g. "Oil leak at cylinder head gasket" |
| `plant` | String | Manufacturing location, e.g. "Plant A - Dharuhera" |
| `product` | String | Part/product affected |
| `reportedBy` | String | Who raised the issue |
| `status` | String | Current step: `D1` → `D2` → ... → `D8` → `CLOSED` |
| `priority` | String | `Critical / High / Medium / Low` |

### `DStep`
One record per D-step per case. Stores both the AI-generated suggestion and the human-approved content separately.

| Field | Type | Description |
|-------|------|-------------|
| `stepNumber` | Int | 1–8 |
| `content` | String (JSON) | The current saved content (may be human-edited) |
| `aiSuggested` | String (JSON) | The original AI output, preserved for comparison |
| `approved` | Boolean | Whether a human has approved this step |
| `approvedBy` | String | Name/role of approver |
| `approvedAt` | DateTime | When it was approved |

### `AuditLog`
Every write to a step creates an immutable log entry.

| Action | When |
|--------|------|
| `CASE_CREATED` | New case submitted |
| `AI_SUGGESTED` | AI generated content for a step |
| `HUMAN_EDITED` | Engineer modified the AI suggestion |
| `APPROVED` | Step approved and case advanced |

---

## API Reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/cases` | List all cases with steps |
| `POST` | `/api/cases` | Create a new case |
| `GET` | `/api/cases/:id` | Get one case with all steps and audit log |
| `PATCH` | `/api/cases/:id` | Update case metadata |
| `POST` | `/api/cases/:id/steps` | Save step content (AI suggestion or human edit) |
| `PUT` | `/api/cases/:id/steps` | Approve a step → advances case status |
| `POST` | `/api/ai/suggest` | Ask AI to generate content for a specific D-step |
| `POST` | `/api/ai/similar` | Find similar closed cases by keyword match |

---

## AI Integration

The AI layer lives in `lib/gemini.ts` and is a thin wrapper around any OpenAI-compatible API.

### Configuration (environment variables)

```bash
LLM_BASE_URL=http://localhost:6655   # Your LLM endpoint (default: local)
LLM_API_KEY=your-key-here            # API key (optional for local models)
LLM_MODEL=gpt-4.1-mini              # Model name to use
```

You can point this at:
- A local model server (Ollama, LM Studio, vLLM)
- OpenAI's API (`https://api.openai.com`, model `gpt-4o`)
- Any other OpenAI-compatible endpoint

### How the AI generates each step

When an engineer clicks **"Generate with AI"**, the frontend calls `POST /api/ai/suggest` with:
- `stepNumber` — which D-step (1–8)
- `context` — an object containing the case metadata plus all previously completed steps

The server selects a **step-specific prompt template** (defined in `app/api/ai/suggest/route.ts`), injects the context, and calls the LLM. Each prompt instructs the model to respond with **only valid JSON** matching a defined schema for that step.

**Context cascade** — each step's prompt includes output from earlier steps:
- D3 receives D2's problem statement and severity
- D4 receives D2's root issue and D3's containment actions
- D6 receives D4's root cause
- D7 receives D4 root cause + D6 corrective actions
- D8 receives D4 root cause + D6 actions + D7 preventive actions

This means later steps get richer, more accurate suggestions because they build on approved prior work.

### Step prompt schemas (what the AI returns)

| Step | Key fields returned |
|------|-------------------|
| D1 | `teamLeader`, `members[]` (name, role, department), `rationale` |
| D2 | `problemStatement`, `what`, `when`, `where`, `who`, `howMany`, `isNot`, `severity`, `customerImpact` |
| D3 | `immediateActions[]` (action, owner, dueDate, status), `stockHold`, `customerNotification`, `effectivenessCheck` |
| D4 | `fishbone` (effect + 6 categories), `fiveWhy[]` (5 iterations), `rootCause`, `escapeCause` |
| D5 | `verificationMethods[]`, `evidenceRequired[]`, `conclusion` |
| D6 | `actions[]` (action, owner, targetDate, priority, status), `implementationPlan`, `successCriteria` |
| D7 | `systemChanges[]`, `similarProcesses[]`, `trainingRequired`, `documentUpdates[]`, `controlPlan` |
| D8 | `summary`, `keyLearnings[]`, `teamAcknowledgment`, `lessonsLearned`, `closureDate`, `effectiveness` |

---

## The Fishbone Diagram

D4 (Root Cause Analysis) includes a live-rendered **Ishikawa (Fishbone) diagram** built as an SVG React component (`components/FishboneDiagram.tsx`).

- Rendered entirely in the browser — no image generation, no external service
- 6 standard manufacturing categories: **Man, Machine, Material, Method, Measurement, Environment**
- AI populates 2–3 causes per category from the problem context
- Color-coded by category, responsive width, dark theme

---

## Human-in-the-Loop Workflow

The system is built around the principle that **AI suggests, humans decide**.

```
AI generates step content
        │
        ▼
Engineer reviews the structured output
        │
   ┌────┴────────────────────┐
   │                         │
   ▼                         ▼
Edit any field          Accept as-is
   │                         │
   └────────────┬────────────┘
                │
                ▼
        Click "Approve & Continue"
                │
                ▼
     Step marked approved in DB
     Case status advances to next D-step
     AuditLog entry written
                │
          (if D8 approved)
                ▼
          Case → CLOSED
```

The audit trail preserves both the original AI suggestion (`aiSuggested`) and the final approved content (`content`) separately in the database, so you can always see what the AI proposed vs. what the engineer actually approved.

---

## Getting Started

### Prerequisites
- Node.js 18+
- An LLM endpoint (local or cloud — see AI Configuration above)

### Setup

```bash
# 1. Install dependencies
npm install

# 2. Run database migrations (creates dev.db)
npx prisma migrate dev

# 3. (Optional) Load sample cases to see the app with data
npm run seed

# 4. Start the dev server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Environment variables

Create a `.env.local` file in the project root:

```bash
LLM_BASE_URL=http://localhost:6655
LLM_API_KEY=your-api-key
LLM_MODEL=gpt-4.1-mini
```

If these are not set, defaults are used (localhost:6655, no key, gpt-4.1-mini).

### Available scripts

| Command | What it does |
|---------|-------------|
| `npm run dev` | Start development server with Turbopack hot reload |
| `npm run build` | Production build |
| `npm run start` | Run the production build |
| `npm run seed` | Load 2 sample closed cases into the database |
| `npx prisma studio` | Open a GUI to browse the database |
| `npx prisma migrate dev` | Apply schema changes and recreate the database |

---

## Dashboard Features

The main dashboard (`/`) shows:

- **Stats bar** — Total cases, Open cases, Closed cases, Critical cases
- **Pipeline overview** — Count of cases at each D-step (D1 through CLOSED), color-coded
- **Cases table** — All cases with problem title, plant/product, priority badge, current stage, progress bar (approved steps / 8), and creation date

---

## Key Design Decisions

**SQLite over Postgres** — Zero-infrastructure setup. The database is a single file (`prisma/dev.db`). Swap to Postgres by updating `schema.prisma` datasource provider and the connection URL when scaling.

**Content stored as JSON strings** — Each D-step's structured data is serialized to JSON in the `content` column. This avoids a proliferation of tables while keeping all step schemas flexible. The UI parses and re-serializes on every read/write.

**OpenAI-compatible interface** — The LLM client is not tied to any specific provider. Swap the model and base URL via environment variables without touching any code.

**Audit trail as separate table** — `AuditLog` is append-only. Every state transition (AI suggestion, human edit, approval) is captured with before/after snapshots, giving a complete history for compliance and review purposes.

**AI suggestion preserved separately** — `DStep.aiSuggested` stores the raw AI output and is never overwritten. `DStep.content` holds the current working version. This makes it possible to diff what changed and revert to the AI baseline.
