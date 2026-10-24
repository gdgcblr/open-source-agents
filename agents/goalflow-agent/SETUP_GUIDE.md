# GoalFlow — Local Setup & Open-Source Quickstart Guide

This guide provides step-by-step instructions for setting up, configuring, and running **GoalFlow** locally on your machine following open-source best practices.

---

## 📋 System Prerequisites

* **Python 3.11 or higher** (Required by Google ADK)
  * Verify your version:
    ```bash
    python3 --version
    ```
  * If you need Python 3.11+:
    * **macOS (Homebrew)**: `brew install python@3.11`
    * **Ubuntu / Debian**: `sudo apt update && sudo apt install python3.11 python3.11-venv`
    * **Windows**: Download Python 3.11+ from [python.org](https://www.python.org/downloads/)
* **Git** installed on your system.

---

## 🚀 Step-by-Step Installation

### Step 1: Clone the Repository
```bash
git clone https://github.com/gdgcblr/open-source-agents.git
cd open-source-agents/goalflow-agent
# (Or navigate to your local goalflow-agent folder)
```

### Step 2: Create a Virtual Environment
Isolating dependencies ensures a clean, conflict-free setup:
```bash
python3.11 -m venv .venv
```

### Step 3: Activate the Virtual Environment
* **On macOS / Linux:**
  ```bash
  source .venv/bin/activate
  ```
* **On Windows (Command Prompt):**
  ```cmd
  .venv\Scripts\activate.bat
  ```
* **On Windows (PowerShell):**
  ```powershell
  .venv\Scripts\Activate.ps1
  ```

### Step 4: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install -e . --no-build-isolation
```

---

## 🔑 Step 5: Get Your Free Gemini API Key

You can use GoalFlow with a **100% free Gemini API key** from Google AI Studio (no credit card or paid Google Cloud account required):

1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Sign in with your personal or work Google account.
3. Click the blue **"Get API key"** button in the upper-left menu.
4. Click **"Create API key in new project"**.
5. Copy the generated key.

---

## ⚙️ Step 6: Configure Environment Variables

1. Copy the example configuration template:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` in any text editor:
   ```env
   # Paste your Gemini API key:
   GEMINI_API_KEY=AIzaSy...your_actual_key_here

   # Recommended free-tier model:
   GEMINI_MODEL=gemini-2.0-flash

   # Local database path:
   GOALFLOW_DB_PATH=goalflow.db
   ```
> **Security Note**: `.env` is automatically listed in [`.gitignore`](file:///Users/chandana/Desktop/goalflow-agent/.gitignore). Never commit your API key or personal reflection database to GitHub.

---

## 🎮 Step 7: Launch GoalFlow

Start the interactive GoalFlow shell:
```bash
python3 -m goalflow.cli
# or simply:
goalflow
```

You will be greeted by the welcome banner:
```text
====================================================================
        GoalFlow - Personal Growth & Goal-Reflection AI Agent
====================================================================
Type 'help' to see available commands, or type any message to chat.
Type 'exit' to quit.

goalflow> 
```

---

## 🧪 Step 8: Run the Test Suite (Zero Cost)

GoalFlow comes with an automated test suite verifying database integrity, hierarchy calculations, and agent guardrails using in-memory mocks (zero paid API calls):

```bash
pytest -v
```

Expected output:
```text
tests/test_agent_logic.py::test_agent_initialization PASSED
tests/test_agent_logic.py::test_self_doubt_retrieval_with_saved_achievements PASSED
tests/test_agent_logic.py::test_self_doubt_retrieval_with_empty_history PASSED
tests/test_agent_logic.py::test_reflection_does_not_prematurely_complete_goals PASSED
tests/test_agent_logic.py::test_mocked_agent_chat_stream PASSED
tests/test_agent_logic.py::test_command_suggestion_routing PASSED
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

============================== 22 passed in 0.46s ==============================
```

---

## 🛠️ Troubleshooting & FAQ

### Q: Can I use GoalFlow completely offline without an API key?
**Yes!** If no `GEMINI_API_KEY` is provided, GoalFlow gracefully switches to **Offline Deterministic Mode**. All goal management (`add-goal`, `list-goals`, `update-goal`), milestones (`achievements`), math progress reviews (`progress`), check-ins (`check-in`), and database backups (`backup`) function 100% locally with zero internet connection.

### Q: Why do I get `ModuleNotFoundError: No module named 'google.adk'`?
Ensure you have activated your virtual environment where the dependencies were installed:
```bash
source .venv/bin/activate
```

### Q: How do I backup or export my data?
Simply type `backup` inside the GoalFlow shell, or copy the `goalflow.db` file to a secure flash drive or backup folder.

### Q: How do I completely wipe my data?
Type `clear-data` inside the GoalFlow shell and confirm by typing `DELETE`.
