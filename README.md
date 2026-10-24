# The Illustrated Primer

> An adaptive, Socratic AI tutor inspired by Neal Stephenson's *The Diamond Age* that maintains a child's evolving epistemic state and teaches through personalized narrative allegories.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Modern LLM-based tutors act like search engines: they immediately give away final answers to math and reading problems, lose track of a child's learning struggles across turns, and lack pedagogical scaffolding.
- **Intended Users**: Young learners (ages 5–10) learning basic phonics, reading, and arithmetic; parents seeking a patient, one-on-one Socratic companion; educators tracking a child's Zone of Proximal Development (ZPD).

### Key Features
- **Persistent Epistemic State**: Tracks the student's real-time knowledge graph, active learning struggles, mastered concepts, and personal interests in a structured profile (`student_profile.json`).
- **Strict Socratic Scaffolding**: Constrained by design to never give away direct answers to arithmetic or spelling queries. It guides the child through guided discovery, sensory metaphors, and progressive hints.
- **Narrative Allegory Engine**: Binds foundational skills (counting, phonics, reasoning) into personalized, unfolding storybook quests tailored to the child's life.
- **Autonomous State Mutation**: Executes real-time tool calling (`update_learning_ledger`) to dynamically promote mastered skills and log observations directly from conversational breakthroughs.
- **Dual-Loop Inspection UI**: A warm storybook interface paired with a live "Primer's Memory" sidebar that lets educators and judges observe state transitions in real time.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: Google ADK (`google-adk`), Google GenAI SDK (`google-genai`)
- **Frontend / Interface**: Streamlit
- **Models**: Gemini 3.8 Flash / Gemini 3.5 Flash
- **Persistence**: Structured local JSON Epistemic State Store

---

## Architecture & Data Flow

The project follows a **Dual-Loop Supervisor** architecture with boundary hooks:

[Child / Parent Input]|v+-------------------------------+       Reads State|     Root Supervisor Agent     | <===================+ [Persistent State]|  (Socratic & Story Scaffolding|                      | (student_profile.json)+---------------+---------------+                      ||                                      ||-- (Skill Mastered / Struggling?) ---+ Tool Call:|                                      update_learning_ledger()v[Streamlit Book UI]|v[Live Memory Sidebar Rerenders]
1. **Input**: The child submits an answer, question, or story tangent.
2. **Contextualization**: The agent loads the active epistemic profile (reading level, math level, current struggles).
3. **Socratic Generation**: The model answers using guided narrative hints rather than raw solutions.
4. **Autonomous Mutation**: If the child demonstrates mastery, the model invokes `update_learning_ledger` to update the profile on disk.
5. **UI Synchronization**: Streamlit displays the response and immediately updates the live memory sidebar.

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.10 or higher
- A Google Gemini API Key from [Google AI Studio](https://aistudio.google.com/apikey)
- A terminal with `pip` or virtual environment capabilities

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd primer_agent
Set up virtual environment & install dependencies:Bashpython -m venv .venv

# Windows (PowerShell):
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install google-adk google-genai streamlit python-dotenv
Configure Environment Variables:Create a .env file in the project root:BashGEMINI_API_KEY="your-google-api-key-here"
Configuration & Environment VariablesVariable NameRequiredDefaultDescriptionGEMINI_API_KEYYesNoneGoogle AI Studio Gemini API KeyMODEL_NAMENogemini-3.8-flashPrimary Gemini model identifierHow to RunOption 1: Storybook Web Interface (Recommended)Launch the interactive Streamlit UI with the live memory sidebar:Bashstreamlit run app.py
Open your browser at http://localhost:8501.Option 2: ADK Native Web PlaygroundRun the native Google ADK agent inspector:Bashadk web .
Open your browser at http://localhost:8000.Example Input & OutputExample InputChild: "I have 7 clockwork gears on my desk, but a squirrel stole 3 of them! How many do I have left?"Example OutputPrimer: "A mischievous squirrel indeed, Nell! Imagine your 7 polished brass gears lined in a row along the mossy stone.If you close your eyes and take 3 away with your hand, count backwards from seven with me: six, five... what is the gear your finger lands upon?"(In the sidebar, student_profile.json registers that the child is actively working through subtraction under 10.)How to TestAutomated VerificationTest if your Gemini API key and dependencies are functioning:Bashpython -c "from google import genai; client = genai.Client(); print(client.models.generate_content(model='gemini-3.8-flash', contents='Say ready').text)"
Manual Demo Steps (For Reviewers & Judges)Launch streamlit run app.py.Inspect the Primer Memory sidebar to confirm initial struggles (subtraction from 10, the 'th' blend).Enter: "Is the answer 4 gears?"Confirm that:The Primer praises your reasoning without sounding robotic.The tool call executes in the background.The sidebar refreshes, removing subtraction from 10 from active struggles and adding it to Mastered Skills.Known LimitationsLocal File Concurrency: State is currently persisted in a local JSON file (student_profile.json), which is designed for single-session use rather than multi-tenant concurrent writes.Text-Only MVP: The prototype currently runs on text chat; multimodal live audio prosody is reserved for upcoming releases.Model Availability: Requires access to recent Gemini Flash endpoints (gemini-3.8-flash or gemini-3.5-flash).Security & Privacy ConsiderationsSecrets Handling: API keys are loaded via local .env files and environment variables, never hardcoded into source or committed to source control.Child-Safe Guardrails: The supervisor prompt is explicitly instructed to divert scary, harmful, or out-of-scope discussions back to benign narrative quests.Data Minimization: Learner state captures only educational milestones, active skills, and pedagogical progress—no sensitive personal identification data is collected.Future Improvements[ ] Real-Time Socratic Jury Node: Asynchronous auditor agent scoring pedagogical warmth and scaffolding adherence on every turn.[ ] Procedural SVG Etchings: Dynamic inline storybook illustrations generated on-the-fly alongside text.[ ] Multimodal Voice In/Out: Integrating the Gemini Live API for real-time speech and emotional prosody suited for pre-readers.[ ] FSRS Spaced Repetition: Graph-based memory modeling to revisit mastered concepts at optimal intervals.LicenseThis project is contributed under the repository's open-source license.


Demo:

<img width="1912" height="1005" alt="image" src="https://github.com/user-attachments/assets/f553021b-762f-4d71-8802-60d0b2a6b484" />

# 📖 The Illustrated Primer

> **An epistemic, adaptive Socratic tutor inspired by Neal Stephenson’s *The Diamond Age*, featuring dynamic student modeling and real-time LLM-as-a-Jury pedagogical alignment.**

[![Model: Gemini 3.8 Flash](https://img.shields.io/badge/Model-Gemini%203.8%20Flash-blue.svg)](https://ai.google.dev/)
[![Framework: Google ADK](https://img.shields.io/badge/Framework-Google%20ADK-orange.svg)](https://adk.dev/)
[![Evaluation: LLM--as--a--Jury](https://img.shields.io/badge/Evaluation-Socratic%20Jury-green.svg)](#-llm-as-a-jury-pedagogical-evaluator)

---

## 💡 Executive Summary & Philosophy

In Neal Stephenson’s *The Diamond Age*, a child is given the *Illustrated Primer*—an interactive book that doesn't just drill answers, but actively reshapes itself around who the child is becoming. 

Standard LLM chat applications fail fundamentally as educational tutors:
- **The Homework Solver Trap:** They immediately blurt out answers ($5 + 3 = 8$) rather than cultivating reasoning.
- **Statelessness:** They do not maintain a longitudinal model of the child's *Zone of Proximal Development (ZPD)* across sessions.
- **Unbounded Hallucination:** They lack dedicated outer-loop evaluation nodes to verify child safety and pedagogical warmth.

**The Illustrated Primer** solves this by implementing a **Dual-Loop Supervisor architecture**:
1. **The Socratic Engine (Inner Loop):** Translates curricular milestones into interactive allegorical micro-stories.
2. **Autonomous Epistemic Memory (State Mutation):** Uses function-calling tools to modify learning ledgers without human intervention.
3. **The Socratic Jury (Outer Loop):** An independent judge model evaluating pedagogical rigor and student mastery on every interaction.

---

## 🏛️ System Architecture

```text
                             [ Child / Student Input ]
                                        |
                                        v
                            +-----------------------+
        Reads Profile       |  Socratic Supervisor  |
+=========================> |  (Gemini 3.8 Flash)   |
|                           +-----------+-----------+
|                                       |
|               +-----------------------+-----------------------+
|               |                                               |
|               v                                               v
|      [ Tool: update_ledger ]                         [ Story Weaver Agent ]
|      (Detects Mastery & Modifies)                    (Generates Allegories)
|               |                                               |
|               +-----------------------+-----------------------+
|                                       |
|                                       v
|                           [ Socratic Child Response ]
|                                       |
|                                       v
|                       +-------------------------------+
|                       |    LLM-as-a-Jury Evaluator    |
|                       | (Validates Rigor & Warmth)    |
|                       +---------------+---------------+
|                                       |
+=======================================+  (Mutates Learner Profile on disk)
                                        |
                                        v
                          [ Dynamic Streamlit UI Update ]


✨ Core Engineering Innovations1. Persistent Epistemic Student ModelingUnlike generic agents that rely purely on context-window history, the Primer persists a structured cognitive profile (student_profile.json). It isolates:Active Struggles: Concepts currently in the student's frontier (e.g., "the 'th' blend", "subtraction from 10").Mastered Skills: Verified competencies systematically promoted out of the active struggle ledger.Narrative Anchors: Episodic interests used to contextualize abstract math/reading puzzles.2. Autonomous State Mutation via Function CallingWhen a child demonstrates comprehension, the Primer does not merely say "Good job." It autonomously invokes the update_learning_ledger tool:Dynamically moves concepts from struggles $\rightarrow$ mastered.Appends qualitative audit logs directly to the persistent store.3. ⚖️ LLM-as-a-Jury Pedagogical EvaluatorEvery conversational exchange is audited asynchronously by an isolated judge node (jury.py) using structured schema enforcement:Socratic Rigor (1–5): Verifies that the model guided through questions and sensory clues rather than revealing solutions.Pedagogical Warmth (1–5): Ensures patient, encouraging, age-appropriate prose.Mastery Verification (Boolean): Deterministically asserts whether the child solved the obstacle independently.

