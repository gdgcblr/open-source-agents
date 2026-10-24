# GoalFlow — Personal Growth & Goal-Reflection AI Agent

GoalFlow is a grounded, privacy-preserving personal growth companion built with **Python**, **Google's Agent Development Kit (ADK)**, and **Gemini**.

Unlike generic motivational chatbots that output hollow quotes, GoalFlow anchors its guidance in **your actual history**: tracking your yearly, monthly, weekly, and daily goals in a local SQLite database, extracting daily reflections, preserving your verified milestones, and presenting concrete evidence of your progress when you experience self-doubt.

---

## 📚 Quick Documentation Index

* **[Project Overview & Components Deep-Dive](file:///Users/chandana/Desktop/goalflow-agent/PROJECT_OVERVIEW.md)**: Comprehensive breakdown of why GoalFlow exists and how its 7 core components work (Goal Hierarchy, "Remember the Good Moments", Daily Reflection, Deterministic Progress, Gentle Check-ins, Intelligent Router, Local Privacy).
* **[Local Setup & Quickstart Guide](file:///Users/chandana/Desktop/goalflow-agent/SETUP_GUIDE.md)**: Step-by-step local installation instructions following open-source standards.
* **[Contributing Guidelines](file:///Users/chandana/Desktop/goalflow-agent/CONTRIBUTING.md)**: Guide for contributing pull requests to the open-source repository.

---

## 🌟 Core Features

- **Hierarchical Goal Management & Reminders**: Organize yearly, monthly, weekly, and daily goals. Smaller goals link directly to larger goals, enabling automated progress rollups and stalled-goal alerts.
- **Natural-Language Daily Reflection**: Share freeform reflections about your day. The agent extracts achievements and blockers, suggests one realistic focus for tomorrow, and guards against marking tasks complete without explicit user confirmation.
- **"Remember the Good Moments" (Achievement Memory)**: Stores actual milestones, completed goals, and learned skills. When you express self-doubt (*"I feel like I am not improving"*), the agent retrieves your real records rather than generating empty cheerleading or hallucinated statistics.
- **Deterministic Progress Reviews**: Uses Python math (not LLM guesswork) for completion percentages, parent-goal progress rollups, and stalled goal detection.
- **Gentle Check-ins & Motivation**: Simple local check-in tracking that celebrates showing up without guilt or shame for missed days.
- **Intelligent Command Router**: Natural language input is met with contextual AI coaching + automatic guidance to the exact CLI command needed.
- **100% Local Privacy**: All personal reflections, goals, and achievements reside in a local SQLite database (`goalflow.db`). No personal history is uploaded to cloud databases.

---

## 🏗️ Architecture & Design Philosophy

GoalFlow enforces a strict boundary between **deterministic operations** and **generative intelligence**:

```
+-------------------------------------------------------------------+
|                        User via CLI Shell                         |
+---------------------------------+---------------------------------+
                                  |
            +---------------------+---------------------+
            | (Natural Language)                        | (Direct Commands)
            v                                           v
+-----------------------+                   +-----------------------+
|  ADK Agent (Gemini)   |                   |  Deterministic Logic  |
|  - Reflection parser  |                   |  - Progress rollups   |
|  - Empathetic coach   |                   |  - Stalled detector   |
|  - Grounding rules    |                   |  - Local reminders    |
+-----------+-----------+                   +-----------+-----------+
            | (Tool Calls)                              |
            +---------------------+---------------------+
                                  |
                                  v
                    +---------------------------+
                    | Controlled Database Tools |
                    | (Pure Python functions)   |
                    +---------------------------+
                                  |
                                  v
                    +---------------------------+
                    | Local SQLite Database     |
                    | (goals, reflections,      |
                    |  achievements, check-ins) |
                    +---------------------------+
```

### Key Architectural Decisions:
1. **No Raw SQL to the LLM**: The Gemini model only interacts with the database through strictly typed Python tool functions (`create_goal`, `list_goals`, `record_daily_reflection`, `retrieve_relevant_achievements`, `get_progress_summary`).
2. **Zero-Hallucination Grounding**: If the user expresses self-doubt and no achievements are logged yet, the agent explicitly states this and helps the user log their first milestone. It is prohibited by system prompt from inventing milestones or statistics.
3. **Conservative Goal Completion**: Intention is never treated as completion. The agent never marks a goal finished unless explicitly confirmed by the user.

---

## 🔑 How to Get a Free Gemini API Key (No Credit Card Required)

You do **not** need a paid Google Cloud account to use GoalFlow. Google provides a generous free tier for Gemini via **Google AI Studio**:

1. Visit [Google AI Studio](https://aistudio.google.com/).
2. Sign in with any standard Google account.
3. Click **"Get API key"** in the top navigation.
4. Click **"Create API key in new project"**.
5. Copy your generated key and place it into your `.env` file (see below).

> **Note**: Even without an API key, GoalFlow's entire deterministic engine (goal management, hierarchy rollups, achievements, local reflections, check-ins, and backups) works 100% offline!

---

## 🚀 Installation & Setup

### Prerequisites
* **Python 3.11+** (required by `google-adk`)
* **macOS / Linux / Windows**

### 1. Clone the repository
```bash
git clone https://github.com/gdgcblr/open-source-agents.git
cd open-source-agents/goalflow-agent
# (or cd into your local goalflow-agent folder)
```

### 2. Create a virtual environment
```bash
python3.11 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
pip install -e . --no-build-isolation
```

### 4. Configure environment variables
Copy the template and insert your free Gemini API key:
```bash
cp .env.example .env
```
Edit `.env`:
```env
GEMINI_API_KEY=your_actual_api_key_here
GEMINI_MODEL=gemini-2.0-flash
GOALFLOW_DB_PATH=goalflow.db
```

---

## 💻 Interactive Command-Line Experience

Start GoalFlow:
```bash
python3 -m goalflow.cli
# or if installed in editable mode:
goalflow
```

### Shell Commands:
| Command | Description |
|---|---|
| `add-goal` | Create a new yearly, monthly, weekly, or daily goal with optional parent linking. |
| `list-goals` | Display all goals in an indented hierarchy with completion status. |
| `update-goal` | Change goal status (`pending`, `in_progress`, `completed`, `abandoned`). |
| `reflect` | Record a daily reflection and receive structured analysis & priority suggestions. |
| `encourage` | Request evidence-based perspective and grounding from saved milestones. |
| `achievements` | View verified accomplishments or record a new milestone (`achievements add`). |
| `progress` | View mathematically calculated progress percentages and stalled goals. |
| `check-in` | Record your daily presence check-in. |
| `backup` | Create a timestamped backup copy of your local SQLite database. |
| `clear-data` | Permanently erase personal records (privacy reset). |
| `help` | Display command help and usage tips. |
| `exit` / `quit` | Gracefully exit GoalFlow. |

### Natural Conversational Interaction:
You can also type natural thoughts directly at the prompt:
```text
goalflow> I feel like I am falling behind and haven't achieved anything this week.
```
The agent recognizes self-doubt, queries your verified achievement history, and responds with empathetic, evidence-backed perspective.

---

## 🧪 Running Tests (Zero API Cost)

All database operations, mathematical progress rollups, tool wrappers, and agent guardrails are tested using in-memory SQLite fixtures and mocked model runners. The test suite runs **with zero paid API calls**:

```bash
pytest -v
```

Output:
```text
tests/test_agent_logic.py::test_agent_initialization PASSED
tests/test_agent_logic.py::test_self_doubt_retrieval_with_saved_achievements PASSED
tests/test_agent_logic.py::test_self_doubt_retrieval_with_empty_history PASSED
tests/test_agent_logic.py::test_reflection_does_not_prematurely_complete_goals PASSED
tests/test_agent_logic.py::test_mocked_agent_chat_stream PASSED
tests/test_db.py::test_init_db PASSED
tests/test_db.py::test_create_and_get_goal PASSED
tests/test_db.py::test_goal_hierarchy PASSED
tests/test_db.py::test_persistence_across_reconnect PASSED
tests/test_db.py::test_update_goal_status PASSED
tests/test_db.py::test_invalid_inputs PASSED
tests/test_db.py::test_check_in_recording PASSED
tests/test_progress.py::test_goal_progress_without_subgoals PASSED
tests/test_progress.py::test_goal_progress_with_subgoals PASSED
tests/test_progress.py::test_level_summary PASSED
tests/test_progress.py::test_stalled_goals_detection PASSED
tests/test_tools.py::test_tool_create_and_list_goals PASSED
tests/test_tools.py::test_tool_update_goal_status PASSED
tests/test_tools.py::test_tool_record_daily_reflection PASSED
tests/test_tools.py::test_tool_record_and_retrieve_achievements PASSED
tests/test_tools.py::test_tool_get_progress_summary PASSED

============================== 21 passed in 0.51s ==============================
```

---

## 🔒 Privacy, Data Retention & Backups

1. **Local Storage**: All your reflections, goals, and achievements are stored in `goalflow.db` on your local filesystem.
2. **Context Minimization**: When interacting with the Gemini API, GoalFlow sends only the immediate reflection or the relevant retrieved milestones—never your entire database history.
3. **Backing Up Your Records**:
   * Run `backup` within the CLI to create a timestamped copy (e.g., `goalflow_backup_YYYYMMDD_HHMMSS.db`).
   * Or simply copy the `goalflow.db` file to a secure backup drive.
4. **Deleting Your Data**:
   * Run `clear-data` from within the CLI and confirm by typing `DELETE`.
   * Or delete the `goalflow.db` file directly from your disk.

---

## 🗺️ Limitations & Future Improvements

- **Local Reminders**: In this version, reminders are maintained via local check-in tracking (`check-in`). A future version may add system cron notifications.
- **Single-User Architecture**: Designed for single-user personal growth on local machines.
- **Multimodal Reflection**: Future iterations may support voice reflection notes and screenshot attachments of completed milestones.

---

## 📄 License

This project is licensed under the Apache 2.0 License.
