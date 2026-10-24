# LifeAdmin MCP

> A local-first personal deadline assistant: manage reminders with MCP tools and optionally use a Gemma 4 agent through Ollama and Google ADK.

---

## Interactive Application Flow

Explore the standalone [interactive application walkthrough](application-flow.html) for a visual, end-to-end explanation of the CLI, MCP server, optional local Gemma agent, SQLite persistence, safety behavior, evaluations, and current limitations.

---

## Overview

### Problem Statement & Intended Users

People lose track of bills, appointments, renewals, and document expiry dates. LifeAdmin keeps those deadlines in a local SQLite database and exposes clear tools to an MCP-compatible client. It is for individuals who want a lightweight reminder list and developers who want a reproducible example of an MCP server connected to a tool-using local model.

The MCP server and database work without an AI model. The Gemma/ADK integration is an optional natural-language interface, not a requirement for storing or retrieving reminders.

### Key Features

- Use the `lifeadmin` command directly for day-to-day reminders; no AI client or model required.
- Get a daily agenda of overdue and due-today tasks with one command.
- Add, list, edit, and complete dated reminders through MCP.
- Persist reminders locally in SQLite across restarts.
- Use the machine's local date and timezone to ground relative-date interpretation.
- Optional Google ADK agent connected to a local Gemma 4 E4B model through Ollama.
- Offline unit and MCP transport tests, plus ADK agent evaluation cases.
- Ask for clarification instead of creating a reminder from an unclear date.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+
- **Agent Framework / Core Library**: Google ADK; official Python MCP SDK
- **Models**: Gemma 4 E4B through Ollama (optional)
- **External APIs / Tools**: Local Ollama HTTP API; SQLite

### Model choice

Use `gemma4:e4b` as the default. The development machine checked for this project has 14 GB system memory and a Radeon 860M with 2 GB reported graphics memory. E4B is a practical balance for local tool use; the 12B/26B/31B workstation variants would be a poor fit for that memory budget. Expect CPU-heavy inference if the model does not fit in available GPU memory. If E4B is too slow, `gemma4:e2b` is a smaller fallback, with potentially weaker date interpretation and tool selection.

Gemma 4 is not bundled or downloaded by Python setup. Ollama must be installed and recent enough to support Gemma 4; update the existing Ollama installation if `ollama pull gemma4:e4b` or `ollama show gemma4:e4b` reports an unsupported model.

---

## Architecture & Data Flow

```text
Natural-language request
        ↓
Google ADK agent (optional) ── Gemma 4 E4B via local Ollama
        ↓ MCP stdio
LifeAdmin MCP server ── validation and reminder tools
        ↓
SQLite file on this machine
```

The MCP server is independently usable from any compatible client. AI interpretation happens in ADK; database validation and persistence are deterministic Python/SQLite operations.

---

## Prerequisites

- Python 3.11 or later.
- Ollama for the optional Gemma agent. Use an Ollama release that supports Gemma 4.
- Several GB of free disk space to download Gemma 4 E4B; inference speed depends on available memory and hardware.

---

## Installation & Setup

From PowerShell, in the repository root, install the AI agent and development/test tools:

```powershell
Set-Location tools\lifeadmin-mcp
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[agent,dev]"
```

If Python 3.14 is not installed, substitute any Python 3.11+ interpreter, for example `py -3.12`.
For the direct CLI and MCP server without the AI agent, install only the lightweight dependencies with `python -m pip install -e ".[dev]"`.

Install and verify the model:

```powershell
ollama --version
ollama pull gemma4:e4b
ollama show gemma4:e4b
```

The model information should list `tools` under capabilities. If this Ollama installation does not recognize Gemma 4, update Ollama from [ollama.com/download](https://ollama.com/download), restart it, and retry. Do not use an Ollama cloud model if reminders must stay local.

Set the model and Ollama URL for the current PowerShell session:

```powershell
$env:LIFEADMIN_MODEL = "gemma4:e4b"
$env:OLLAMA_API_BASE = "http://localhost:11434"
```

Alternatively, copy `.env.example` to `.env` in the project directory and edit the values. The ADK agent loads that file. To use another model supported by Ollama, set `LIFEADMIN_MODEL` to its local model tag.

---

## Configuration & Environment Variables

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `LIFEADMIN_MODEL` | No | `gemma4:e4b` | Ollama model tag used by the ADK agent. |
| `OLLAMA_API_BASE` | For the agent | `http://localhost:11434` | Local Ollama API base URL. |
| `LIFEADMIN_DB_PATH` | No | `~/.lifeadmin/reminders.sqlite3` | SQLite file path. Parent directories are created as needed. |

Copy `.env.example` if you want a starting point for local settings. Never put credentials or private data in the sample file.

---

## How to Run

### Connect an MCP client

The server uses MCP stdio. After installing the project in its virtual environment, configure your MCP client to launch:

- **Command**: the full path to `tools\lifeadmin-mcp\.venv\Scripts\python.exe`
- **Arguments**: `["-m", "lifeadmin_mcp.server"]`
- **Working directory**: the `tools\lifeadmin-mcp` project directory

For VS Code, add the following to `.vscode/mcp.json` at the repository root, replacing the workspace path if needed:

```json
{
  "servers": {
    "lifeadmin": {
      "type": "stdio",
      "command": "${workspaceFolder}\\tools\\lifeadmin-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "lifeadmin_mcp.server"],
      "cwd": "${workspaceFolder}\\tools\\lifeadmin-mcp"
    }
  }
}
```

The server exposes:

| Tool | Purpose |
| :--- | :--- |
| `add_reminder` | Save a title and ISO calendar date (`YYYY-MM-DD`), with optional time, category, and notes. |
| `list_reminders` | List upcoming, overdue, completed, or all reminders. |
| `find_reminders` | Find reminders by title text to safely identify one before editing or completing it. |
| `update_reminder` | Edit supplied fields for an existing reminder; set `clear_due_time=true` to remove its time. Empty category/notes clear those fields. |
| `mark_completed` | Mark a reminder completed without deleting it. |
| `get_current_date` | Return the host's current local date and timezone for date interpretation. |

### Use LifeAdmin directly (no model required)

The command-line interface is the quickest way to use LifeAdmin day to day:

```powershell
lifeadmin add "Renew vehicle insurance" --due 2026-11-10 --category documents
lifeadmin today
lifeadmin list --status upcoming
lifeadmin find insurance
lifeadmin update --title insurance --due 2026-11-12
lifeadmin complete --title insurance
```

Dates use ISO `YYYY-MM-DD` format and times use local `HH:MM`. `today` shows overdue items and items due today. Update or complete by ID (`--id`) or by a title phrase that must match exactly one reminder (`--title`); ambiguous title matches are rejected without changing data. Set notes/category to an empty quoted string to clear them; use `lifeadmin update --id <id> --clear-time` to remove a due time.

### Run the Google ADK agent

From `tools\lifeadmin-mcp` with the virtual environment active and Ollama running:

```powershell
adk web
```

Select `lifeadmin_agent` in the ADK web interface. Try:

> Remind me to renew my vehicle insurance on 10 November 2030.

The assistant should save the reminder and confirm the interpreted date. It should ask before writing when a date or task is too vague. The database defaults to `%USERPROFILE%\.lifeadmin\reminders.sqlite3`; set `LIFEADMIN_DB_PATH` to use a different location.

### Run the guided live AI demo

For a presentation, run the two-turn demo with one command from `tools\lifeadmin-mcp` in PowerShell, using the project's virtual environment:

```powershell
.\.venv\Scripts\python.exe -m lifeadmin_agent.demo
```

This sends two real prompts through Google ADK, your installed local Ollama model, the LifeAdmin MCP server, and SQLite. It prints the configured model and Ollama endpoint, the agent responses, MCP tool calls and arguments, and direct SQLite verification. The first prompt asks for an upcoming vehicle-insurance deadline; the second uses a vague date and verifies that it did not change the database. The demo uses and keeps an isolated database under your temporary directory, leaving personal reminders untouched. At the end it prints commands to inspect that database with the CLI.

Ollama must be running and the configured model must already be installed. The defaults are `gemma4:e4b` and `http://localhost:11434`; append `--help` to the command above to select another model or local Ollama endpoint. This is a live, model-dependent demonstration, so response wording and inference time can vary.

---

## Example Input & Output

### Example Input

```text
Remind me to renew my vehicle insurance on 10 November 2030.
```

### Example MCP result

```json
{
  "title": "Renew my vehicle insurance",
  "due_date": "2030-11-10",
  "due_time": null,
  "status": "open"
}
```

The real response also includes a reminder ID and creation/update timestamps. The assistant confirms the saved date; it does not invent a time.

---

## How to Test and Evaluate

Run the deterministic suite; it does not make model requests:

```powershell
pytest
```

It covers SQLite persistence and CRUD, date validation, status filters, update/clear behavior, eval scoring/date helpers, and an actual MCP stdio client/server exchange.

Run the deterministic suite before submitting changes. It does not download or call an LLM; run `lifeadmin-eval` locally when changing agent or model behavior.

For model-backed evaluations, keep Ollama running and make sure the selected model is pulled. Run:

```powershell
lifeadmin-eval
```

This project-owned runner does not depend on ADK's optional evaluation package or cloud credentials. It runs eight scenarios and checks the exact tool-call trajectory and arguments, user-facing response, and final SQLite state. Each case starts from isolated reminder data, and all eval data is stored in a temporary database that is deleted afterward.

Choose another local Ollama model or save a JSON report:

```powershell
lifeadmin-eval --model llama3.2:latest --output eval-results.json
```

Run only selected cases while tuning a prompt or model:

```powershell
lifeadmin-eval --case resolve_yearless_upcoming_date --case complete_identified_reminder
```

The report records the model, per-case tool calls, user-facing response, state/trajectory scores, and pass/fail result. Reports are git-ignored because they contain model-generated text. Evaluations are probabilistic; use them to compare changes and inspect failures, not as a guarantee of perfect date understanding. Record the model tag and Ollama version when comparing runs.

---

## Known Limitations

- This first version stores reminders but does not send push notifications, synchronize calendars, or support recurring schedules.
- The `today` command is a daily agenda, not a background notification service; open it to review what's due.
- Dates are calendar dates; reminders without a time do not imply a time of day.
- “Upcoming” and “overdue” use the host machine's local calendar date.
- The AI integration needs a local Ollama service and a model with tool-calling support. Model responses and latency vary by hardware and model release.
- The prototype is a personal, single-user database; it does not yet provide accounts, encryption, or multi-user access controls.

---

## Security & Privacy Considerations

- **Secrets Handling**: The project does not require provider API keys. `.env.example` contains no credentials.
- **Data Privacy**: Reminder data is stored locally in SQLite. With a locally hosted Ollama model, prompts are sent to the local Ollama service; do not configure a cloud model if you require local-only inference.
- **Safety**: The MCP server only reads or changes its LifeAdmin database. The agent must use the explicit tools for changes and ask for clarification when dates are ambiguous.
- **Backups**: The database contains personal data; protect its local file and backups as you would other private records.

---

## License

This project is contributed under the repository's MIT License.
