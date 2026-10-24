# ASO Optimizer Agent

> A multi-agent system that optimizes your Google Play Store listing — title, description, and keywords — using a Hub & Spoke architecture with guardrails and a Gemini → Gemma → rule-based fallback chain.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Writing an effective Play Store listing is hard. Poor ASO (App Store Optimization) means fewer downloads, even for great apps. Most developers write their listing once and never optimize it.
- **Intended Users**: Mobile app developers, indie hackers, and product teams who want to improve their app's discoverability and conversion rate on Google Play Store without hiring an ASO consultant.

### Key Features
- **Hub & Spoke Architecture**: A central hub orchestrator fans out to three specialized spoke agents (keyword, description, title) running **in parallel**, then aggregates the results.
- **Input Guardrail**: Scans the original listing for harmful content and false advertising before any LLM is called.
- **Output Guardrail**: Validates the optimized output — enforces the 50-character Play Store title limit and removes misleading claims that the model may have introduced.
- **Fallback Chain**: Every spoke tries `gemini-2.0-flash` first → falls back to `gemma-3-27b-it` → falls back to a deterministic rule-based response. The agent always returns an output.
- **Demo Mode**: Run instantly with `npm run demo` — no API key required.

---

## Technical Stack

- **Language & Runtime**: TypeScript / Node.js 18+
- **Agent Framework**: Custom Hub & Spoke pattern (inspired by Google ADK architecture)
- **Primary Model**: Gemini 2.0 Flash (`gemini-2.0-flash`) via `@google/genai`
- **Fallback Model**: Gemma 3 (`gemma-3-27b-it`) via `@google/genai`
- **External APIs**: Google Generative AI SDK (`@google/genai`), `dotenv`

---

## Architecture & Data Flow

```
[Developer's App Listing]
         │
 ┌───────▼───────────────────────────┐
 │      INPUT GUARDRAIL              │  Blocks harmful/spam listings
 │  (hub responsibility)             │  Warns about misleading claims
 └───────┬───────────────────────────┘
         │ passes
 ┌───────▼───────────────────────────┐
 │      HUB ORCHESTRATOR             │  Fans out in parallel
 └──┬────────────┬───────────────┬───┘
    │            │               │
[Spoke 1]    [Spoke 2]      [Spoke 3]
Keyword      Description    Title
Agent        Agent          Agent
    │            │               │
 Gemini →     Gemini →       Gemini →
 Gemma  →     Gemma  →       Gemma  →
 Rules        Rules          Rules
    │            │               │
 ┌──▼────────────▼───────────────▼───┐
 │      OUTPUT GUARDRAIL             │  Validates title length (≤50 chars)
 │  (hub responsibility)             │  Checks for false claims in output
 └───────┬───────────────────────────┘
         │
 [ASOReport → Developer]
```

### Fallback Chain (per spoke)
```
Attempt gemini-2.0-flash (up to 2 retries, 15s timeout each)
   │ fails
   ▼
Attempt gemma-3-27b-it (up to 2 retries, 15s timeout each)
   │ fails
   ▼
Rule-based deterministic response (always succeeds)
```

---

## Prerequisites

- Node.js 18 or higher
- npm
- A Google Gemini API key — **optional**, agent runs in rule-based mode without one
  - Free key: https://aistudio.google.com/app/apikey

---

## Installation & Setup

```bash
# 1. Navigate to the project directory
cd agents/aso-optimizer-agent

# 2. Install dependencies
npm install

# 3. (Optional) Configure your API key
# Windows PowerShell:
Copy-Item .env.example .env
# Linux / macOS:
cp .env.example .env
# Then open .env and paste your GEMINI_API_KEY
```

---

## Configuration & Environment Variables

| Variable        | Required | Default | Description                                          |
| :-------------- | :------- | :------ | :--------------------------------------------------- |
| `GEMINI_API_KEY`| No       | *None*  | Gemini API key. Without it, rule-based mode is used. |

---

## How to Run

```bash
# Demo mode — uses a built-in sample app (no API key needed)
npm run demo

# Interactive mode — enter your own app details
npm run dev
```

---

## Example Input & Output

### Input (Demo App — TaskFlow)
```
App Name     : TaskFlow
Title        : TaskFlow - Best Todo List App & Planner in the World
Category     : Productivity
Audience     : Professionals and students
Description  : TaskFlow is a simple to-do list. It is the best app ever made.
               100% free and guaranteed. Download now — #1 app!
```

### Output
```
🏷️  OPTIMIZED TITLE  [38 chars | via gemini-2.0-flash]
  TaskFlow – Smart Task Manager & Planner

🗝️  KEYWORDS  [via gemini-2.0-flash]
  task manager, to-do list, daily planner, productivity app,
  work organizer, reminder app, habit tracker, ...

📝 OPTIMIZED DESCRIPTION  [via gemini-2.0-flash]
  Stay on top of everything with TaskFlow — the task manager
  built for how you actually work.
  ...

🛡️  GUARDRAIL NOTES
  ⚠️  Misleading claim found ("#1 app") — removed from optimized output.
  ⚠️  Misleading claim found ("best app ever") — removed from optimized output.
```

---

## How to Test

```bash
# Test 1: Normal app (should pass all guardrails, show optimization)
npm run demo

# Test 2: Interactive mode with your own app
npm run dev

# Test 3: Guardrail block — modify getDemoListing() in src/index.ts
# to include "hacking tool" in the description — input guardrail will block it
```

---

## Known Limitations

- Gemma model availability depends on your Google AI Studio region and quota.
- Rule-based fallback produces generic output — useful for demos, not production.
- The agent does not fetch live Play Store data; input must be provided manually.
- Output guardrail uses regex, not semantic analysis, for claim detection.

---

## Security & Privacy Considerations

- **Secrets Handling**: API key loaded from `.env` via `dotenv`. `.env` is in `.gitignore`.
- **Data Privacy**: App listing text is sent to Google Generative AI API in non-mock mode.
- **Safety**: Agent does not execute shell commands or write files.

---

## Future Improvements

- [ ] Fetch current listing automatically from Play Store URL.
- [ ] Add competitor analysis spoke (analyze top-ranked apps in same category).
- [ ] Web UI for non-technical users.
- [ ] Support Apple App Store (different character limits and rules).
- [ ] Add semantic guardrails using Perspective API.

---

## Author

**Amrutha** — contributed at GDG Cloud Bengaluru: Road to DevFest 2026 (Fork. Build. Merge.)

---

## License

*This project is contributed under the repository's open-source license.*
