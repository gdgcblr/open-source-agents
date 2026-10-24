# Multi-Agent Editorial Team (`agents/multi-agent-editorial-team`)

> A hierarchical multi-agent collaborative pipeline where Planner, Researcher, Writer, and Reviewer agents collaborate with a critique-and-revision reflection loop to publish citation-backed technical articles.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Generating high-stakes technical documentation, research papers, or architectural briefs using a single prompt-response LLM call frequently produces hallucinated claims, structurally shallow sections, and unverified assumptions. Without dedicated separation of concerns and iterative editorial critique, AI-generated content cannot be trusted in production.
- **Intended Users**: Software architects, technical writers, developer advocates, researchers, and engineering teams requiring peer-reviewed, citation-grounded technical dossiers.

### Key Features
- **Hierarchical 4-Agent Architecture**:
  1. **Planner Agent**: Decomposes complex topics into target audiences, structural outlines, and search strategies.
  2. **Researcher Agent**: Gathers verified factual findings via live DuckDuckGo web search without requiring paid search API keys.
  3. **Writer Agent**: Composes comprehensive prose adhering to the blueprint and evidence dossier.
  4. **Reviewer / Critic Agent**: Grades draft quality across a 4-dimension rubric (0–100) and issues targeted revision feedback.
- **Critique & Revision Reflection Loop**: The Writer and Reviewer collaborate in an iterative loop: if draft v1 scores below the pass threshold (default 85/100), the Writer produces draft v2 directly addressing each critique point.
- **Circuit Breaker Anti-Deadlock Guard**: A strict `max_revisions` cap (default: 2 turns) prevents infinite rejection ping-pong between Writer and Reviewer.
- **Interactive Executive HTML Dashboard**: Generates a self-contained, offline-compatible HTML dossier featuring quick metric widgets, a collaborative DAG visualizer, draft evolution tabs (v1 vs. v2), an inter-agent message timeline, and print-to-PDF formatting.
- **Model Context Protocol (MCP) Server**: Exposes the complete collaborative team as a standard MCP tool (`run_editorial_team`) for Claude Desktop, Cursor, and Antigravity.
- **Zero-Key Offline Mock Mode**: Includes an offline `--mock` provider so reviewers and automated CI environments can verify multi-agent collaboration immediately without an API key.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+ (Tested on Python 3.13)
- **Agent Orchestration**: StateGraph State-Machine Pattern with Pydantic Contracts (`TeamState`, `AgentMessage`, `ReviewVerdict`)
- **LLM Support**: Google Gemini API (`gemini-2.5-flash`, `gemini-1.5-flash`, `gemini-1.5-pro`) via official `google-genai` SDK with fallback to offline mock engine
- **Protocols & Integrations**:
  - `FastMCP` (Model Context Protocol stdio server)
  - `duckduckgo-search` (Live web discovery without paid API keys)
  - `pydantic` (Typed inter-agent message passing and state management)
  - `pytest` (Automated integration test suite)

---

## Architecture & Data Flow

```
[User Topic / Prompt]
          │
          ▼
┌────────────────────────────────────────────────────────┐
│            EditorialOrchestrator (State Machine)       │
│                                                        │
│   1. PLANNER AGENT                                     │
│      Decomposes Topic ──► ArticlePlan (Outlines & Qs)  │
│                                │                       │
│   2. RESEARCHER AGENT          ▼                       │
│      DuckDuckGo Search ─► EvidenceItem[] Dossier       │
│                                │                       │
│   3. WRITER AGENT              ▼                       │
│      Synthesizes Evidence ─► Draft v1                  │
│                                │                       │
│   4. REVIEWER / CRITIC AGENT   ▼                       │
│      Rubric Evaluation (0-100) ──► ReviewVerdict       │
│                                                        │
│      ┌──────────────────────────────────────────────┐  │
│      │ Score < 85 & Turns < MaxRevisions:           │  │
│      │ └──► REVISE ──► Writer drafts v2             │  │
│      │                                              │  │
│      │ Score >= 85 or MaxRevisions Reached:         │  │
│      │ └──► APPROVED ──► Publication                │  │
│      └──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
          │
          ▼
┌────────────────────────────────────────────────────────┐
│                   Published Artifacts                  │
│   - reports/editorial_<topic>_<timestamp>.md           │
│   - reports/editorial_<topic>_<timestamp>.html         │
└────────────────────────────────────────────────────────┘
```

---

## Prerequisites

Before running the multi-agent pipeline:
- **Python 3.10 or higher** installed.
- **pip** package manager.
- *(Optional for live mode)*: Free **Google Gemini API Key** from [Google AI Studio](https://aistudio.google.com). Offline mock mode works with zero keys.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/multi-agent-editorial-team
   ```

2. **Set up a virtual environment and install dependencies:**
   - **Windows (PowerShell):**
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     pip install -r requirements.txt
     ```
   - **Linux / macOS:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     pip install -r requirements.txt
     ```

3. **Configure Environment Variables:**
   - **Windows:**
     ```powershell
     Copy-Item .env.example -Destination .env
     ```
   - **Linux / macOS:**
     ```bash
     cp .env.example .env
     ```
   Set your `GEMINI_API_KEY`:
   ```bash
   GEMINI_API_KEY=AIzaSy...
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Optional in `--mock` / Required in live | *None* | Google Gemini API Key from Google AI Studio. |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Gemini model for Planner, Writer, and Reviewer reasoning. |
| `MAX_REVISIONS` | No | `2` | Maximum allowable critique-revision cycles (circuit breaker). |
| `CRITIQUE_PASS_SCORE`| No | `85` | Quality score threshold (0–100) required for Reviewer approval. |
| `SEARCH_MAX_RESULTS` | No | `4` | Max search findings per query for the Researcher Agent. |
| `OUTPUT_DIR` | No | `reports` | Directory where published Markdown and HTML dossiers are stored. |

---

## How to Run

### 1. Instant Offline Test (Zero API Key Needed)
Run the full 4-agent collaborative pipeline with mock simulation:
```bash
python main.py --mock --topic "Consensus Protocols in Multi-Agent AI"
```

### 2. Live Research & Drafting Run
Run with live Gemini models and DuckDuckGo web discovery:
```bash
python main.py --topic "Architecting Scalable Microservices with Go"
```

### 3. Custom Revision Depth & Pass Score
Tune the editorial quality gate and revision limits:
```bash
python main.py --topic "Zero Knowledge Proofs in 2026" --max-revisions 3 --pass-score 90
```

### 4. Interactive Console Mode
Launch interactive REPL mode:
```bash
python main.py --interactive
```

### 5. Launch as Model Context Protocol (MCP) Server
Expose the collaborative editorial team to Claude Desktop, Cursor, or Antigravity:
```bash
# Verify tool bindings via self-test
python mcp_server.py --test

# Launch MCP stdio server
python mcp_server.py
```

**Claude Desktop Configuration (`claude_desktop_config.json`)**:
```json
{
  "mcpServers": {
    "editorial-team": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "agents/multi-agent-editorial-team"
    }
  }
}
```

---

## Example Input & Output

### Example Command
```bash
python main.py --mock --topic "Consensus Protocols in Multi-Agent AI"
```

### Example Console Log
```
===========================================================================
👥 Launching Multi-Agent Editorial Pipeline on: 'Consensus Protocols in Multi-Agent AI'
[Mode] OFFLINE MOCK MODE (Zero API key required)
[Rules] Max Revisions: 2 | Pass Threshold: 85/100
===========================================================================

[13:44:17] 🚀 [PLANNER] Starting: Decomposing topic 'Consensus Protocols in Multi-Agent AI' into structural plan.
[13:44:17] ✓  [PLANNER] Completed: Plan ready: 'Comprehensive Guide to Consensus Protocols in Multi-Agent AI'

[13:44:17] 🚀 [RESEARCHER] Starting: Executing web discovery for 3 queries.
[13:44:17] ✓  [RESEARCHER] Completed: Gathered 3 evidence items.

[13:44:17] 🚀 [WRITER] Starting: Drafting initial article (v1).
[13:44:17] ✓  [WRITER] Completed: Draft v1 completed (1266 chars).

[13:44:17] 🚀 [REVIEWER] Starting: Auditing draft v1 against quality rubric.

[13:44:17] 🚀 [WRITER] Starting: Revising draft (v2) to address Reviewer critiques.
[13:44:17] ✓  [WRITER] Completed: Draft v2 revised (1507 chars).

[13:44:17] 🚀 [REVIEWER] Starting: Auditing draft v2 against quality rubric.
[13:44:17] ✓  [REVIEWER] Completed: Draft v2 APPROVED (Score: 92/100)

===========================================================================
🎉 Editorial Collaboration Completed!
[Quality Score] 92 / 100 (APPROVED)
[Revisions Made] 1 / 2
[Markdown Article] reports/editorial_consensus_protocols_in_multi-agent_ai_20261024_134417.md
[HTML Dashboard]   reports/editorial_consensus_protocols_in_multi-agent_ai_20261024_134417.html
[Telemetry] Duration: 0.01s | Evidence: 3 items | Messages: 5
===========================================================================
```

---

## How to Test

Run the automated integration and unit test suite using `pytest`:

```bash
# Run all tests
pytest tests

# Run with verbose test step output
pytest -v tests
```

Expected test result:
```
agents/multi-agent-editorial-team/tests/test_agents.py::test_planner_agent PASSED [ 11%]
agents/multi-agent-editorial-team/tests/test_agents.py::test_researcher_agent PASSED [ 22%]
agents/multi-agent-editorial-team/tests/test_agents.py::test_writer_initial_and_revision PASSED [ 33%]
agents/multi-agent-editorial-team/tests/test_agents.py::test_reviewer_rubric_and_gates PASSED [ 44%]
agents/multi-agent-editorial-team/tests/test_pipeline.py::test_full_pipeline_mock_execution PASSED [ 55%]
agents/multi-agent-editorial-team/tests/test_pipeline.py::test_circuit_breaker_max_revisions_limit PASSED [ 66%]
agents/multi-agent-editorial-team/tests/test_pipeline.py::test_empty_topic_raises_invalid_topic_error PASSED [ 77%]
agents/multi-agent-editorial-team/tests/test_pipeline.py::test_publication_export_dual_artifacts PASSED [ 88%]
agents/multi-agent-editorial-team/tests/test_pipeline.py::test_mcp_server_bindings PASSED [100%]

============================== 9 passed in 1.75s (100%) ==============================
```

---

## Known Limitations

- **Revision Deadlock Safeguard**: To prevent endless debate cycles between Writer and Reviewer, `max_revisions` is hard-capped at 5 (default 2).
- **DuckDuckGo Rate Limits**: When running large batches of research queries in rapid succession, DuckDuckGo may throttle requests; the Researcher Agent implements graceful fallbacks to preserve pipeline progress.
- **Context Limits**: Articles with extensive source counts are summarized to ensure token budgets stay well within standard model context windows.

---

## Security & Privacy Considerations

- **Zero Hardcoded Secrets**: All API keys must be passed via environment variables or `.env`. `.env` is strictly ignored by Git.
- **No Unsafe Execution**: Agents communicate strictly through typed Pydantic messages; no shell commands or dynamic `eval()` execution is permitted.
- **Path Sanitization**: Report slugs are sanitized against directory traversal attacks.

---

## Future Improvements

- [ ] Add dynamic multi-reviewer consensus (e.g., Security Reviewer + SEO Reviewer + Technical Auditor voting).
- [ ] Support local LLMs via Ollama for zero-cost, private offline multi-agent execution.
- [ ] Add PDF document attachment ingestion for the Researcher Agent.

---

## License

This project is contributed under the repository's open-source [MIT License](../../LICENSE).
