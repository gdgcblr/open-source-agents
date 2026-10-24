# Coding Interview Mock Agent — Frontend UI

A modern, responsive React + Tailwind CSS web interface simulating a Google Software Engineering technical interview.

---

## 🌟 Features

- **Google SWE Interviewer Dialogue**: Interactive real-time chat interface with typing indicators and conversational stages.
- **Stage Progression Stepper**: Visual tracking across all 7 interview stages:
  1. *Introduction*
  2. *Problem Presentation*
  3. *Approach & Complexity Discussion*
  4. *Coding Implementation*
  5. *Code Review & Edge Case Walkthrough*
  6. *Google-Scale Follow-up*
  7. *Hiring Committee Report*
- **Problem & Bounds Drawer**: Problem description, examples, and dynamically revealed constraints as the candidate asks clarifying questions.
- **Multi-Language Code Editor**: Built-in editor with tab-indentation support and syntax styles for **Python**, **JavaScript**, **C++**, and **Java**.
- **Execution Console**: Live execution runner capturing `stdout`, `stderr`, runtime duration in milliseconds, and exit codes.
- **Hiring Committee Evaluation Modal**: Displays overall score (out of 10), Google Hiring Recommendation (*Strong Hire*, *Hire*, *Leaning Hire*, *Leaning No Hire*, *No Hire*), 6-competency rubric breakdown, strengths, growth areas, and recommended study topics.

---

## 🚀 Setup and Development

### Prerequisites
- Node.js (v18 or higher recommended)
- npm or pnpm

### 1. Install Dependencies
```bash
cd agents/coding-interview-mock-agent/ui
npm install
```

### 2. Start Development Server
```bash
npm run dev
```
The application will launch at `http://localhost:5173`.
All `/api/*` network requests are automatically proxied to the backend at `http://127.0.0.1:8000`.

### 3. Build for Production
```bash
npm run build
```
This generates the optimized static bundle in `ui/dist`, which can be served directly by FastAPI.

