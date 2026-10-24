# GoalFlow — Purpose, Philosophy & Architectural Components

This document outlines the **vision, philosophy, and architectural components** of GoalFlow. It serves as a comprehensive reference for users, contributors, and maintainers.

---

## 1. What is GoalFlow?

**GoalFlow** is an open-source, local-first AI agent designed to serve as a **personal growth and goal-reflection companion**. 

It is built with **Python**, **Google's Agent Development Kit (ADK)**, and **Gemini**.

### The Problem It Solves
Most people set ambitious yearly, monthly, weekly, and daily goals, but struggle with consistent tracking:
* **Paper journals** are manual, hard to query, and easily forgotten.
* **Standard to-do list apps** become overwhelming backlogs that generate guilt rather than clarity.
* **Generic AI chatbots** respond with hollow, copy-pasted motivational quotes (*"Believe in yourself!"*) that fail to help when you are genuinely discouraged.

### The GoalFlow Philosophy
GoalFlow is built on three core tenets:
1. **Evidence-Based Encouragement**: When you doubt your progress, the agent proves your growth by retrieving **real milestones** saved in your personal history. It never fabricates wins or statistics.
2. **Deterministic Boundaries**: Math, completion percentages, database records, and status updates belong to strict Python logic. Generative AI is reserved for empathy, summarization, and cognitive coaching.
3. **Local Privacy**: Your personal goals, struggles, and reflections belong to you. All data resides in a local SQLite file (`goalflow.db`) on your machine.

---

## 2. Core Architectural Components

GoalFlow is composed of seven distinct, integrated components:

```
+-------------------------------------------------------------------------------+
|                                GoalFlow CLI                                   |
+---------------------------------------+---------------------------------------+
                                        |
       +--------------------------------+--------------------------------+
       | Natural Language Prompts                                        | Explicit Commands
       v                                                                 v
+-----------------------------+                           +-----------------------------+
|    Component 6:             |                           |    Component 1:             |
|    Natural Language Router  |                           |    Goal Hierarchy Manager   |
|    & Command Mentorship     |                           |    (Yearly/Monthly/Weekly)  |
+--------------+--------------+                           +--------------+--------------+
               |                                                         |
               v                                                         |
+-----------------------------+                                          |
|    ADK Gemini Agent         |                                          |
|    (Google ADK + Gemini)    |                                          |
+--------------+--------------+                                          |
               |                                                         |
       +-------+-------+                                                 |
       |               |                                                 |
       v               v                                                 v
+--------------+ +--------------+                         +-----------------------------+
| Component 2: | | Component 3: |                         |    Component 4:             |
| Achievement  | | Daily        |                         |    Deterministic Progress   |
| Memory       | | Reflection   |                         |    & Stalled Detector       |
| ("Good       | | & Guardrails |                         +--------------+--------------+
|  Moments")   | +-------+------+                                        |
+-------+------+         |                                               |
        |                |                                               |
        +----------------+-----------------------+-----------------------+
                                                 |
                                                 v
                                  +-----------------------------+
                                  |    Component 7:             |
                                  |    Local SQLite Engine      |
                                  |    (goalflow.db)            |
                                  +-----------------------------+
                                                 ^
                                                 |
                                  +--------------+--------------+
                                  |    Component 5:             |
                                  |    Gentle Check-in &        |
                                  |    Streak Tracker           |
                                  +-----------------------------+
```

---

### Component 1: Goal Hierarchy & Relational Linking
* **Files**: [`models.py`](file:///Users/chandana/Desktop/goalflow-agent/src/goalflow/models.py), [`db.py`](file:///Users/chandana/Desktop/goalflow-agent/src/goalflow/db.py)
* **CLI Command**: `add-goal`, `list-goals`, `update-goal`
* **Purpose**:
  Allows organizing goals across four distinct temporal tiers:
  * **Yearly**: Long-term directional goals (e.g., *"Master AI Agent Development"*).
  * **Monthly**: Strategic milestones (e.g., *"Build 2 open-source agents with Google ADK"*).
  * **Weekly**: Tactical focus areas (e.g., *"Implement tool calling and tests"*).
  * **Daily**: Concrete actionable steps (e.g., *"Write test fixtures for SQLite"*).
* **Key Mechanism**:
  Smaller goals link to larger parent goals via foreign keys (`parent_id`). Completing a daily action automatically increments the progress percentage of its parent weekly and monthly goals.

---

### Component 2: "Remember the Good Moments" — Personal Achievement Memory
* **Files**: [`tools.py`](file:///Users/chandana/Desktop/goalflow-agent/src/goalflow/tools.py), [`agent.py`](file:///Users/chandana/Desktop/goalflow-agent/src/goalflow/agent.py)
* **CLI Command**: `achievements`, `encourage`
* **Purpose**:
  This is the emotional anchor of GoalFlow. People frequently suffer from "negativity bias" and imposter syndrome—forgetting how much they have accomplished over months of effort.
* **Key Mechanism**:
  * Whenever a goal is completed or a win occurs, it is permanently logged in the `achievements` table with timestamps, categories, and personal notes.
  * When you say: *"I feel like I'm falling behind"* or *"I haven't achieved anything"*, the agent detects self-doubt, calls `retrieve_relevant_achievements`, and quotes **verified historical facts** back to you.
* **Anti-Fabrication Policy**:
  If your history is empty, the agent honestly admits it has no stored records yet and invites you to log your first win. It **never fabricates milestones**.

---

### Component 3: Daily Reflection & Safety Guardrails
* **Files**: [`agent.py`](file:///Users/chandana/Desktop/goalflow-agent/src/goalflow/agent.py), [`tools.py`](file:///Users/chandana/Desktop/goalflow-agent/src/goalflow/tools.py)
* **CLI Command**: `reflect`
* **Purpose**:
  Provides an end-of-day cognitive download where you can write freely about what went well and what went wrong.
* **Key Mechanism**:
  * Extracts completed tasks and notable wins.
  * Identifies obstacles, distractions, or fatigue without shame or judgment.
  * Formulates **one single, realistic priority for tomorrow** to avoid decision paralysis.
* **Strict Guardrail**:
  The agent will **never mark a goal as completed** merely because you "intended to do it" or "spent time on it". Completion requires explicit confirmation.

---

### Component 4: Deterministic Progress Review & Stalled Detector
* **Files**: [`progress.py`](file:///Users/chandana/Desktop/goalflow-agent/src/goalflow/progress.py)
* **CLI Command**: `progress`
* **Purpose**:
  Accurate quantitative feedback on your progress without LLM hallucination.
* **Key Mechanism**:
  * Pure Python calculations for completion rates ($0-100\%$) across all four tiers.
  * Scans for **stalled goals**: any goal in `pending` or `in_progress` status that has remained untouched for more than 7 days, or is past its target date.

---

### Component 5: Gentle Motivation & Daily Check-in
* **Files**: [`db.py`](file:///Users/chandana/Desktop/goalflow-agent/src/goalflow/db.py), [`cli.py`](file:///Users/chandana/Desktop/goalflow-agent/src/goalflow/cli.py)
* **CLI Command**: `check-in`
* **Purpose**:
  A zero-friction daily ritual that celebrates the act of showing up.
* **Key Mechanism**:
  * Records today's presence in the `check_ins` table.
  * If you miss days, GoalFlow has a **strict no-shaming policy**: it never lectures you on missed days, but rather helps you downsize your immediate next action into an easy 5-minute win.

---

### Component 6: Intelligent Natural Language Router & Command Mentorship
* **Files**: [`agent.py`](file:///Users/chandana/Desktop/goalflow-agent/src/goalflow/agent.py), [`cli.py`](file:///Users/chandana/Desktop/goalflow-agent/src/goalflow/cli.py)
* **Purpose**:
  Bridges natural conversation with structured CLI commands.
* **Key Mechanism**:
  * When you type freeform sentences (e.g., *"yearly goals are create an ai gent"*), the system does not reject your input or silently guess database parameters.
  * Instead, it provides contextual coaching and **actively directs you to the exact command** (e.g., `💡 Recommended Command: add-goal`).

---

### Component 7: Local-First Privacy, Backups & Reset
* **Files**: [`db.py`](file:///Users/chandana/Desktop/goalflow-agent/src/goalflow/db.py), [`cli.py`](file:///Users/chandana/Desktop/goalflow-agent/src/goalflow/cli.py)
* **CLI Command**: `backup`, `clear-data`
* **Purpose**:
  Complete data sovereignty and peace of mind.
* **Key Mechanism**:
  * Everything is saved in `goalflow.db`.
  * `backup` generates timestamped database copies for safe keeping.
  * `clear-data` permanently wipes all records after typing `DELETE`.
