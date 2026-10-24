# Coding Interview Mock Agent

> An AI-powered technical interview simulator that mimics an authentic Google Software Engineering (SWE) coding interview with multi-stage evaluation, dynamic constraint discovery, and isolated code execution.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Gemini](https://img.shields.io/badge/Gemini%20API-Google%20GenAI-4285F4.svg)](https://aistudio.google.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev/)
[![TailwindCSS](https://img.shields.io/badge/TailwindCSS-3.4-38B2AC.svg)](https://tailwindcss.com/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Most coding interview preparation resources (such as LeetCode or HackerRank) focus exclusively on passing automated unit tests. However, real-world Google and FAANG technical interviews evaluate candidates on how they think aloud, clarify ambiguous specifications, discover hidden constraints, debate algorithmic trade-offs before writing code, handle edge cases, and adapt to scale-up follow-up scenarios.
- **Intended Users**: Software engineers, computer science students, and interview candidates preparing for technical Data Structures and Algorithms (DSA) interviews at Google, FAANG, and top-tier technology companies.

### Key Features
- **Authentic 7-Stage Interview Flow**: Guides candidates seamlessly from Introduction, Problem Presentation, Approach Discussion, Coding, Code Review, Google-Scale Follow-up, to the final Hiring Committee Evaluation Report.
- **Socratic Google Interviewer Persona**: Powered by Gemini API, the agent never blurts out solutions or writes code for the candidate; it provides Socratic nudges and evaluates communication.
- **Dynamic Constraint Discovery**: Initial problem descriptions do not reveal all boundary constraints upfront. When candidates proactively ask clarifying questions (e.g., empty inputs, negative numbers, duplicates), the interviewer naturally reveals them.
- **Curated Multi-Topic Question Bank**: 19 questions across Easy, Medium, and Hard difficulty covering Arrays, Strings, Linked Lists, Trees, Graphs, BFS/DFS, Dynamic Programming, Sliding Window, Heaps, Tries, and Backtracking.
- **Multi-Language Code Runner**: Sandboxed subprocess execution layer with timeouts supporting **Python**, **JavaScript**, **C++**, and **Java**, capturing `stdout`, `stderr`, runtime duration in milliseconds, and exit codes.
- **Hiring Committee Evaluation**: Rigorous evaluation across 6 Google SWE dimensions (Communication, Problem Solving, Code Quality, Complexity Analysis, Edge Cases, Optimization) producing an overall score out of 10 and hiring recommendations (*Strong Hire*, *Hire*, *Leaning Hire*, *Leaning No Hire*, *No Hire*).
- **Dual Interfaces**: Full-featured React + Tailwind CSS web IDE alongside an interactive Terminal CLI mode (`--cli`).

---

## Technical Stack

List of primary frameworks, languages, models, and external services used:
- **Language & Runtime**: Python 3.10+ (Backend), Node.js 18+ (Frontend UI)
- **Agent Framework / Core Library**: Google GenAI SDK (`google-genai` / `google-generativeai`), FastAPI, Pydantic v2, Uvicorn
- **Models**: Google Gemini 2.5 Flash (`gemini-2.5-flash`), with support for `gemini-2.0-flash` or `gemini-1.5-pro` (and an offline heuristic fallback mode)
- **External APIs / Tools**: Google AI Studio Gemini API, React 18, Tailwind CSS 3.4, Vite, Subprocess execution runner

---

## Architecture & Data Flow

```
[Candidate / Web UI / CLI]
           |
           v
+-----------------------------------------------------------+
|               FastAPI Application (main.py)               |
+-----------------------------+-----------------------------+
                              |
       +----------------------+----------------------+
       |                                             |
       v                                             v
+-----------------------------+       +-----------------------------+
|   Interview State Engine    |       |   Code Execution Service    |
|   (services/interview.py)   |       |  (services/code_runner.py)  |
+--------------+--------------+       +--------------+--------------+
               |                                     |
               | (Stage Progression & Context)       | (Subprocess Isolation)
               v                                     v
+-----------------------------+       +-----------------------------+
|    Prompt & Question Bank   |       | Python / JS / C++ / Java    |
|    (question_bank/ & utils) |       | Compiler & Runtime Execution|
+--------------+--------------+       +-----------------------------+
               |
               v
+-----------------------------------------------------------+
|       Evaluator & Report Service (services/evaluator.py)  |
|          Google Gemini API (gemini-2.5-flash)             |
|              [Offline Heuristic Fallback]                 |
+-----------------------------+-----------------------------+
                              |
                              v
             [Structured Hiring Committee Report]
             [Score / 10 & Hiring Recommendation]
```

### Component Structure
```
agents/coding-interview-mock-agent/
├── README.md                      # Project documentation
├── requirements.txt               # Backend Python dependencies
├── .env.example                   # Environment variables template
├── .gitignore                     # Git ignore rules
├── main.py                        # FastAPI application & CLI entrypoint
│
├── prompts/                       # System Prompts
│   ├── interviewer.txt            # Google Interviewer persona & Socratic rules
│   ├── evaluator.txt              # Hiring Committee 6-dimension evaluation rubric
│   └── followup.txt               # Scalability & systems follow-up generator
│
├── question_bank/                 # Curated DSA questions
│   ├── easy.json                  # Arrays, Strings, Trees, Linked List
│   ├── medium.json                # Graphs, Sliding Window, Heap, Trie, DP
│   └── hard.json                  # Two Pointers, K-Way Merge, Trie+DFS, DP
│
├── services/                      # Decoupled Business Logic
│   ├── interview.py               # Session lifecycle & stage progression state machine
│   ├── evaluator.py               # Gemini API evaluation & heuristic parsing
│   ├── code_runner.py             # Subprocess runner with timeouts & output limits
│   └── report.py                  # Score calculation & Markdown report generator
│
├── models/                        # Pydantic Schemas
│   └── schemas.py                 # Data models for questions, sessions, submissions, reports
│
├── utils/                         # Helper Utilities
│   └── loader.py                  # Disk loader for questions and prompt files
│
├── tests/                         # Pytest Suite
│   ├── test_questions.py          # Schema validation & minimum question count checks
│   └── test_evaluator.py          # Evaluator, parser, runner, and report tests
│
└── ui/                            # React + Tailwind CSS Web Application
    ├── README.md                  # Frontend documentation
    ├── package.json               # NPM package manifest
    ├── vite.config.js             # Vite configuration with API proxy
    ├── index.html                 # HTML entrypoint
    └── src/
        ├── App.jsx                # Main IDE layout & session state
        ├── main.jsx               # React mount root
        ├── index.css              # Tailwind directives & dark scrollbars
        └── components/
            ├── Navbar.jsx         # Header & 7-stage progress stepper
            ├── ProblemDrawer.jsx  # Problem statement & discovered bounds
            ├── ChatFeed.jsx       # Multi-turn conversation feed
            ├── CodeEditor.jsx     # Editor with line numbers & run console
            └── ReportModal.jsx    # Google Hiring Committee Report modal
```

---

## Prerequisites

Before running this project, ensure you have:
- **Python Runtime**: Python 3.10 or higher
- **Node.js Runtime** (for Web UI): Node.js 18+ and npm
- **Package Managers**: `pip` (Python) and `npm` (Node.js)
- **API Key**: Google Gemini API key from [Google AI Studio](https://aistudio.google.com/) *(Optional: an intelligent offline heuristic mode activates automatically if no API key is set)*
- **Optional Compilers**: `node`, `g++`, or `javac` installed if you wish to run JavaScript, C++, or Java code locally.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/coding-interview-mock-agent
   ```

2. **Set up the Python virtual environment & install dependencies:**
   - **On Linux/macOS:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     pip install -r requirements.txt
     ```
   - **On Windows (PowerShell):**
     ```powershell
     python -m venv venv
     .\venv\Scripts\Activate.ps1
     pip install -r requirements.txt
     ```

3. **Install Frontend dependencies:**
   ```bash
   cd ui
   npm install
   cd ..
   ```

4. **Configure Environment Variables:**
   Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and fill in your Gemini API key:
   ```ini
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   GEMINI_MODEL=gemini-2.5-flash
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | No *(Yes for live LLM)* | `your_api_key_here` | API key from Google AI Studio. If omitted, offline heuristic simulator activates. |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Identifier for the Gemini model (`gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-1.5-pro`). |
| `PORT` | No | `8000` | Local network port for the FastAPI backend server. |
| `HOST` | No | `127.0.0.1` | Host address binding for the FastAPI backend. |
| `CODE_EXECUTION_TIMEOUT`| No | `5.0` | Maximum execution time in seconds allowed for candidate code execution. |

---

## How to Run

### 1. Start the Backend API Server
From `agents/coding-interview-mock-agent/`:
```bash
python main.py
```
- The backend starts on `http://127.0.0.1:8000`.
- Interactive Swagger API docs are available at `http://127.0.0.1:8000/docs`.

### 2. Start the Frontend Web UI
In a separate terminal window:
```bash
cd agents/coding-interview-mock-agent/ui
npm run dev
```
- Open `http://localhost:5173` in your browser.
- All `/api/*` endpoints are automatically proxied to the backend on port 8000.

### 3. (Alternative) Run in Interactive Terminal CLI Mode
If you prefer conducting a mock interview directly in your terminal without a browser:
```bash
python main.py --cli
```
- Chat with the interviewer by typing responses.
- Type `:code` to open a multi-line code submission buffer (type `EOF` to submit).
- Type `exit` or `finish` to trigger evaluation and display your final Markdown report.

---

## Example Input & Output

### Example Input
1. **Candidate clarifying question in Chat:**
   > *"Can the input array contain negative numbers or duplicate values? Also, can the array be empty?"*

2. **Candidate code submission (Python):**
   ```python
   class Solution:
       def two_sum(self, nums, target):
           seen = {}
           for i, num in enumerate(nums):
               complement = target - num
               if complement in seen:
                   return [seen[complement], i]
               seen[num] = i
           return []
   ```

### Example Output
1. **Interviewer Response:**
   > *"Great questions to ask before implementing! Yes, the numbers can be negative. The array will have at least 2 elements, and exactly one valid solution is guaranteed to exist. How are you planning to approach the lookup efficiently?"*

2. **Generated Hiring Committee Report:**
   ```markdown
   # 🏛️ Google SWE Coding Interview Feedback Report

   **Candidate:** Candidate  
   **Question:** Two Sum (Arrays - Easy)  

   ## 🎯 Overall Interview Score: 8.4 / 10
   ### Hiring Recommendation: 🟢 HIRE

   ## 📊 Rubric Evaluation Breakdown
   | Competency | Score (out of 10) | Evaluation Rating |
   | :--- | :---: | :--- |
   | Communication | **9/10** | Exceptional |
   | Problem Solving | **9/10** | Exceptional |
   | Code Quality | **8/10** | Good |
   | Complexity Analysis | **9/10** | Exceptional |
   | Edge Cases | **7/10** | Good |
   | Optimization | **9/10** | Exceptional |

   ## ⏱️ Complexity & Technical Assessment
   - **Time Complexity:** `O(N) Time`
   - **Space Complexity:** `O(N) Auxiliary Space`
   - **Correctness:** Correct linear single-pass hash map implementation.

   ## 💪 Key Strengths
   - ✅ Proactive and articulate communication; consistently thought aloud.
   - ✅ Successfully transitioned from brute-force O(N^2) to optimal O(N) hash map.

   ## 🔍 Areas for Growth
   - ⚠️ Overlooked extreme 64-bit integer overflow edge cases.

   ## 🎯 Recommended Practice Topics
   - 📚 Dynamic Programming (State Transitions & Memoization)
   - 📚 Graph Traversal (BFS / DFS & Cycle Detection)
   ```

---

## How to Test

Verify question schemas, heuristic evaluators, JSON extraction, and code execution using the test suite:

```bash
# Run automated pytest suite
pytest tests/ -v
```

### What the Tests Verify:
1. **`tests/test_questions.py`**:
   - Validates that `easy.json`, `medium.json`, and `hard.json` parse into `Question` Pydantic models.
   - Asserts that every difficulty level contains at least 5 complete questions (minimum 15 total; currently 19).
   - Verifies required schema keys (`id`, `title`, `difficulty`, `topic`, `description`, `constraints`, `examples`, `followups`).
2. **`tests/test_evaluator.py`**:
   - Tests robust JSON extraction from Gemini responses (including markdown fenced ` ```json ` blocks).
   - Validates offline heuristic scoring logic and score ranges ($1.0 \le \text{Score} \le 10.0$).
   - Verifies hiring recommendation threshold mappings (`Strong Hire` down to `No Hire`).
   - Verifies code execution handling with timeouts and runtime diagnostics.

---

## Known Limitations

- **Subprocess Code Runner Isolation (MVP)**: Code execution currently runs locally using Python's `subprocess` with timeout and output limits. For production multi-tenant environments, this should be migrated to isolated container sandboxes (e.g., Docker or gVisor) as noted in the roadmap.
- **Language Compiler Requirements**: Executing JavaScript, C++, or Java requires their respective binaries (`node`, `g++`, `javac`) to be installed in the host's `PATH`. If missing, the runner cleanly returns an explanatory message without crashing.
- **Free-Tier Gemini Rate Limits**: When using free-tier Gemini API keys, rapid multi-turn requests may trigger API rate limits. The application handles this by falling back gracefully to the built-in offline heuristic evaluator.
- **Session Storage**: Sessions are persisted as local JSON files inside `sessions/`. This is ideal for single-node development but would require PostgreSQL or Redis for distributed, multi-instance production deployments.

---

## Security & Privacy Considerations

- **Secrets Handling**: API keys and environment variables are loaded exclusively on the backend via `python-dotenv` from `.env`. Secrets are never exposed to the client-side React UI, included in git commits, or hardcoded in source code (`.gitignore` excludes all `.env` files).
- **Data Privacy**: Only interview chat messages and code submissions are sent to the Google Gemini API over secure HTTPS/TLS. No private user file paths, personal data, or unrelated system context are collected or transmitted.
- **Safety**:
  - The code runner executes candidate scripts with strict `subprocess` timeouts (default 5.0 seconds) to prevent infinite loops and `fork` bombs.
  - Standard output and error streams are truncated at 50 KB to prevent buffer flooding attacks.
  - Temporary files created during compilation and execution are automatically removed via `tempfile.TemporaryDirectory`.
  - Detailed instructions and Docker container isolation commands (`--network none`, `--memory 128m`, read-only root) are pre-documented in [`services/code_runner.py`](services/code_runner.py).

---

## Future Improvements

- [ ] **Simulated Video Call (Google Meet Experience)**: Integrate WebRTC-based video calling with an interactive AI interviewer avatar, simulating authentic face-to-face Google Meet interviews with non-verbal feedback and presence indicators.
- [ ] **Real-Time Voice-to-Text (Speech-to-Text / STT)**: Support hands-free "think aloud" candidate dialogue via Web Speech API and Whisper/Gemini audio processing, converting spoken candidate explanations into code comments and dialogue in real time.
- [ ] **Natural Voice Messaging & TTS Audio**: Add neural Text-to-Speech (TTS) audio playback so the Google interviewer speaks questions, interruptions, and hints aloud with realistic cadence, alongside support for asynchronous candidate voice notes.
- [ ] **Docker Sandbox Migration**: Migrate local subprocess execution to rootless Docker / gVisor containers with `--network none` and `--memory 128m`.
- [ ] **Gemini Multimodal Live API (Bidirectional Audio)**: Direct streaming audio integration using Gemini Multimodal Live API over WebSockets for zero-latency conversational back-and-forth.
- [ ] **AST Static Analysis**: Parse Python and Java Abstract Syntax Trees to detect recursion depth, memory leaks, and anti-patterns before executing code.
- [ ] **Collaborative Whiteboard**: Add an interactive canvas for diagramming tree structures, graph traversals, and system architectures.
- [ ] **Level Customization**: Allow candidates to target specific engineering tiers (L3 Junior, L4 Mid-level, L5 Senior, L6 Staff) with dynamically tuned rubric strictness.

---

## License

*This project is contributed under the repository's open-source license.*

