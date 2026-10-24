# Research Assistant Agent

> An autonomous desk-research AI agent powered by Google Gemini and live DuckDuckGo web search that creates citation-backed Markdown reports.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Large language models trained on static datasets cannot reliably answer questions about cutting-edge technologies, newly released APIs, or evolving standards. Single-turn prompt-response setups frequently hallucinate details or fail to verify claims across multiple independent sources.
- **Intended Users**: Software engineers, researchers, students, and AI practitioners who need fast, structured, citation-backed research dossiers without paying for expensive third-party search APIs.

### Key Features
- **Autonomous Multi-Step ReAct Loop**: Breaks high-level research questions into targeted search queries, reviews retrieved observations, scrapes in-depth articles, and synthesizes findings.
- **Zero-Cost Live Web Search**: Connects directly to DuckDuckGo search without requiring paid search API keys (such as Tavily or Google Custom Search).
- **Resilient Web Page Extraction**: Parses real webpage content with boilerplate stripping (removing navigation, scripts, and ads) and token truncation.
- **Interactive Executive HTML Dashboard**: Automatically compiles an interactive, dark-mode briefing dashboard alongside Markdown with quick telemetry stat widgets, table of contents, collapsible source cards, and print-to-PDF styles.
- **Model Context Protocol (MCP) Server**: Exposes the research assistant as an MCP tool (`run_deep_research`, `search_web`, `scrape_webpage`) for instant integration with Claude Desktop, Cursor, and Antigravity.
- **Zero-Key Offline Mock Mode**: Includes an offline `--mock` provider so reviewers and automated CI pipelines can verify end-to-end functionality immediately without needing an API key.
- **Dual Invocation Modes**: Supports single-topic execution via `--topic` and an interactive terminal console via `--interactive`.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+ (Tested on Python 3.13)
- **Agent Framework**: Custom lightweight ReAct (Reasoning + Acting) loop built on Google's official `google-genai` SDK (with fallback support for `google-generativeai`)
- **Models Supported**: `gemini-2.5-flash` (default), `gemini-1.5-flash`, `gemini-1.5-pro`, or built-in offline mock provider
- **External Tools & Libraries**:
  - `duckduckgo-search` (Live web query discovery)
  - `beautifulsoup4` & `requests` (HTML parsing and content cleaning)
  - `python-dotenv` (Sanitized environment variable loading)
  - `pytest` (Automated testing suite)

---

## Architecture & Data Flow

```
[User Topic / CLI Prompt]
          │
          ▼
┌────────────────────────────────────────────────────────┐
│               ResearchAgent (agent/core.py)            │
│                                                        │
│   ┌─────────────────┐       ┌──────────────────────┐   │
│   │  Thought Loop   │◄─────►│ Gemini / Mock Engine │   │
│   └────────┬────────┘       └──────────────────────┘   │
│            │                                           │
│            ▼ Action Dispatch                           │
│   ┌────────────────────────────────────────────────┐   │
│   │ 1. search_web     --> DuckDuckGo Search API    │   │
│   │ 2. scrape_webpage --> HTTP Fetcher & BS4 Parser│   │
│   │ 3. finish_research--> Final Synthesis Exporter │   │
│   └────────────────────────────────────────────────┘   │
│            │                                           │
│            ▼                                           │
│   [Observation Buffer]                                 │
└────────────────────────────────────────────────────────┘
          │
          ▼
┌────────────────────────────────────────────────────────┐
│                   Structured Output                    │
│   - Formatted Terminal Log                             │
│   - reports/research_<topic>_<timestamp>.md            │
└────────────────────────────────────────────────────────┘
```

---

## Prerequisites

Before running the agent, make sure you have:
- **Python 3.10 or higher** installed.
- **pip** package manager.
- *(Optional for live mode)*: A free **Google Gemini API Key** from [Google AI Studio](https://aistudio.google.com). Offline testing requires no key.

---

## Installation & Setup

1. **Navigate to the agent directory:**
   ```bash
   cd agents/research-assistant
   ```

2. **Set up a virtual environment and install dependencies:**
   - **On Windows (PowerShell):**
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     pip install -r requirements.txt
     ```
   - **On Linux / macOS:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     pip install -r requirements.txt
     ```

3. **Configure Environment Variables:**
   Copy the example environment configuration:
   - **Windows:**
     ```powershell
     Copy-Item .env.example -Destination .env
     ```
   - **Linux / macOS:**
     ```bash
     cp .env.example .env
     ```
   Open `.env` in an editor and insert your `GEMINI_API_KEY`:
   ```bash
   GEMINI_API_KEY=AIzaSy...
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | No (in `--mock` mode) / Yes (live mode) | *None* | Google Gemini API key obtained from Google AI Studio. |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Gemini model identifier used for reasoning and synthesis. |
| `MAX_RESEARCH_STEPS` | No | `5` | Maximum number of ReAct loop turns before forcing synthesis. |
| `SEARCH_MAX_RESULTS` | No | `5` | Maximum search results retrieved per web query. |
| `SCRAPE_MAX_CHARS` | No | `4000` | Character cutoff when extracting text from web pages. |
| `OUTPUT_DIR` | No | `reports` | Local directory where generated Markdown dossiers are saved. |

---

## How to Run

### 1. Instant Offline Test (Zero API Key Required)
Run with the `--mock` flag to verify end-to-end functionality without network dependencies or API keys:
```bash
python main.py --mock --topic "Model Context Protocol"
```

### 2. Live Research Run
Run research with live Gemini reasoning and DuckDuckGo web search:
```bash
python main.py --topic "Latest features in Google Agent Development Kit"
```

### 3. Custom Model & Step Limits
Specify a different Gemini model or expand the maximum research steps:
```bash
python main.py --topic "Quantum computing breakthroughs 2026" --model gemini-1.5-pro --max-steps 7
```

### 4. Interactive REPL Mode
Launch interactive mode to research multiple topics in one session:
```bash
python main.py --interactive
```

### 5. Run as Model Context Protocol (MCP) Server
Launch as a standard MCP tool server over stdio for Claude Desktop, Cursor, Antigravity, or other MCP clients:

```bash
# Verify MCP tool bindings via self-test
python mcp_server.py --test

# Launch MCP server in stdio transport mode
python mcp_server.py
```

**Claude Desktop Configuration (`claude_desktop_config.json`)**:
```json
{
  "mcpServers": {
    "research-assistant": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "agents/research-assistant"
    }
  }
}
```

**Exposed MCP Tools**:
- `run_deep_research(topic, mock_mode, max_steps)`: Full research pipeline returning markdown + HTML reports and telemetry.
- `search_web(query, max_results)`: DuckDuckGo live web search.
- `scrape_webpage(url, max_chars)`: Text extractor tool.

---

## Example Input & Output

### Example Command
```bash
python main.py --mock --topic "Model Context Protocol"
```

### Example Console Log
```
======================================================================
[Research] Starting Research Assistant on Topic: 'Model Context Protocol'
[Mode] OFFLINE MOCK MODE (Zero API key required)
======================================================================

[Step 1]
  * Thought: I should begin by searching for high-level overviews and architecture specifications on 'Model Context Protocol'.
  * Action: search_web({'query': 'Model Context Protocol architecture overview and practical guide', 'max_results': 3})
  * Observation: Retrieved 1 search results.
      [1] Search result for: Model Context Protocol architecture overview and practical guide (https://duckduckgo.com/?q=Model+Context+Protocol+architecture+overview+and+practical+guide)

[Step 2]
  * Thought: The search results yielded relevant links. Now I will scrape and extract detailed content from https://duckduckgo.com/?q=Model+Context+Protocol+architecture+overview+and+practical+guide.
  * Action: scrape_webpage({'url': 'https://duckduckgo.com/?q=Model+Context+Protocol+architecture+overview+and+practical+guide', 'max_chars': 2000})
  * Observation [success]: Model Context Protocol architecture overview and practical guide at DuckDuckGo (89 chars)

[Step 3]
  * Thought: I have gathered sufficient factual information on 'Model Context Protocol'. Ready to generate final report.
  * Action: finish_research(...)

======================================================================
[Success] Research Run Completed!
[Output] Report saved to: reports\research_model_context_protocol_20261024_121106.md
[Metrics] Steps taken: 3
======================================================================
```

### Example Output Dossier Preview
```markdown
---
topic: "Model Context Protocol"
generated_at: "2026-10-24 12:11:06"
agent: "open-source-ai / research-assistant"
---

# Research Report: Model Context Protocol

## Executive Summary
This report summarizes research on **Model Context Protocol**. The research synthesizes primary findings, technical architecture, and operational best practices.

## Core Concepts & Technical Architecture
1. **Autonomous Workflows**: Modern implementations leverage tool-calling, reflection loops, and structured output parsing to manage multi-step reasoning.
2. **Context & Protocol Standards**: Emerging standards like Model Context Protocol (MCP) enable decoupled tool and resource provision across diverse models.
3. **Execution Guardrails**: Production agents implement step bounds, token quotas, and strict sandboxing to prevent unbounded execution.

## Annotated Citations & Sources
- [Primary Documentation](https://ai.google.dev/): Google AI and Gemini Developer Documentation.
- [Model Context Protocol Specification](https://modelcontextprotocol.io/): Anthropic Open Source Protocol.
- [DevFest 2026 Agent Hub](https://github.com/gdgcblr/open-source-agents): Community Reference Repository.
```

---

## How to Test

Run the automated test suite using `pytest`:

```bash
# Run all tests
pytest tests

# Run with verbose test step reporting
pytest -v tests
```

Expected test result:
```
agents/research-assistant/tests/test_agent.py::test_search_tool_happy_path PASSED
agents/research-assistant/tests/test_agent.py::test_search_tool_empty_query PASSED
agents/research-assistant/tests/test_agent.py::test_search_tool_max_results_capping PASSED
agents/research-assistant/tests/test_agent.py::test_scraper_invalid_url_schemes PASSED
agents/research-assistant/tests/test_agent.py::test_scraper_valid_url_structure PASSED
agents/research-assistant/tests/test_agent.py::test_sanitize_filename_prevents_path_traversal PASSED
agents/research-assistant/tests/test_agent.py::test_reporter_writes_metrics_frontmatter PASSED
agents/research-assistant/tests/test_agent.py::test_mock_provider_lifecycle PASSED
agents/research-assistant/tests/test_agent.py::test_pydantic_schema_validation PASSED
agents/research-assistant/tests/test_agent.py::test_agent_empty_topic_raises_exception PASSED
agents/research-assistant/tests/test_agent.py::test_agent_json_parsing_resilience PASSED
agents/research-assistant/tests/test_agent.py::test_agent_end_to_end_mock_with_telemetry PASSED
agents/research-assistant/tests/test_enterprise_extensions.py::test_html_dashboard_generation PASSED
agents/research-assistant/tests/test_enterprise_extensions.py::test_html_dashboard_xss_escaping PASSED
agents/research-assistant/tests/test_enterprise_extensions.py::test_toc_extraction PASSED
agents/research-assistant/tests/test_enterprise_extensions.py::test_reporter_saves_both_markdown_and_html PASSED
agents/research-assistant/tests/test_enterprise_extensions.py::test_mcp_server_creation PASSED
agents/research-assistant/tests/test_enterprise_extensions.py::test_mcp_run_deep_research_tool PASSED
============================= 18 passed in 1.44s (100%) ==============================
```

---

## Known Limitations

- **Search Rate Limits**: High-frequency automated queries via DuckDuckGo without delays may trigger temporary IP-level throttling.
- **JavaScript Single Page Applications (SPAs)**: The lightweight scraper uses standard HTTP requests; dynamic client-rendered web apps (e.g., pure React SPAs requiring client-side JS evaluation) will yield minimal text content compared to server-rendered HTML.
- **Context Truncation**: Scraped web pages are truncated at `SCRAPE_MAX_CHARS` (default 4,000 characters) to preserve LLM context budget.
- **Stateless Sessions**: Each CLI run initializes a fresh research session; conversation history is not persisted across distinct process restarts.

---

## Security & Privacy Considerations

- **Zero Committed Secrets**: No API keys or credentials are hardcoded. Credentials must be passed through `.env` or system environment variables, and `.env` is strictly git-ignored.
- **Data Privacy**: Only the search terms and target URLs are transmitted to DuckDuckGo and Google Gemini API. Local files or private datasets are never read or transmitted.
- **Safe Sandboxed Execution**: The agent does not execute shell commands, eval arbitrary code, or access the broader filesystem outside the configured `reports/` folder.

---

## Future Improvements

- [ ] Add PDF document ingestion and parsing for scientific whitepapers.
- [ ] Implement headless browser rendering (e.g., Playwright) for JavaScript-heavy pages.
- [ ] Add multi-agent debate mode (Researcher vs. Fact-Checking Reviewer).
- [x] Export dossiers to standalone interactive HTML dashboards with print-to-PDF styles.

---

## License

This project is contributed under the repository's open-source [MIT License](../../LICENSE).
