# PulseBLR Event Planner

> Discover Bengaluru developer events, infer relevant organiser communities, and plan a feasible itinerary through five model-independent MCP tools. The server is key-free; an optional Gemini chat client is included for manual testing.

## Overview

### Problem Statement & Intended Users

Developers planning a weekend need event links, evidence of relevant communities, and a schedule that accounts for overlaps and transfer time. Event listings often omit an end time or a precise location, so a useful assistant must also explain what it cannot safely schedule.

This tool is for developers and MCP-host builders. It connects a local assistant to the existing public [PulseBLR](https://pulseblr-u9f1.vercel.app/) event service, or to an explicitly fictional offline sample. The new contribution provides a portable stdio package, organiser recommendations, and deterministic scheduling. PulseBLR's existing event aggregation service supplies the optional live data.

### Key Features

- Search public Bengaluru events and retrieve linked event details.
- Discover supported topic and area filters separately from observed trending-topic counts.
- Recommend communities by grouping event organisers and showing supporting event evidence.
- Select up to three events with explicit transfer and duration rules, explaining exclusions.
- Run an offline demo with packaged fictional events and a fixed clock.

## Technical Stack

- **Language & runtime:** Python 3.11 or newer.
- **Core library:** Official Python MCP SDK, pinned to `mcp==2.3.0`; local stdio transport.
- **Models:** None inside this server. The connected MCP host supplies its own model and tool-selection behavior. The optional manual client uses the official Google SDK and your own Gemini API key.
- **External service:** Anonymous public HTTP MCP at `https://pulseblr-u9f1.vercel.app/api/mcp` in live mode.
- **Dependencies:** Declared in `pyproject.toml`; exact runtime and test resolutions are in `requirements.lock` and `requirements-dev.lock`.
- **Cost:** No API key or paid model API is required by the MCP server. The optional Gemini client consumes the quota of your selected Google project/model. Your MCP host may also charge for its own model use. The live service's future pricing, availability, and rate limits are outside this package's control.

## Architecture & Data Flow

```text
User request -> MCP host and its model -> local stdio server
                                          |
                                          +-> live: anonymous public PulseBLR MCP
                                          |
                                          +-> sample: packaged fictional JSON
                                          |
                          validated public events -> filtering/grouping/planning
                                          |
                              structured results -> MCP host -> user
```

The selected source is explicit for the lifetime of the process. Live failures return an error; they never silently become sample results. Every tool result identifies its `data_mode`. Retrieval metadata describes when this server fetched data, not when an organiser last verified a listing.

### Tool surface

| Tool | Purpose | Main arguments |
| --- | --- | --- |
| `search_events` | Find linked public events | `query`, `topics`, `areas`, `when` or `date_from`/`date_to`, `format`, `free_only`, `limit` |
| `get_event` | Retrieve one selected-source event | `event_id` from a previous result |
| `list_topics` | Show supported filters and observed topic counts | Optional named `when` window |
| `recommend_communities` | Group organisers with supporting events | `interests`, `event_ids` **or** discovery filters, `limit` |
| `plan_schedule` | Choose a feasible bounded itinerary | `interests`, `event_ids` **or** discovery filters, `max_events`, `transfer_buffer_minutes`, `duration_policy`, `assumed_duration_minutes` |

Use returned event IDs when referring to “those events.” `event_ids` accepts at most 10 IDs and cannot be combined with discovery filters. Ranking interests remain allowed with IDs. Missing IDs are reported without replacing them with a fresh search. Without IDs, community and schedule tools discover at most 50 candidates.

### Planning rules

- Calendar windows use `Asia/Kolkata` (IST). Default discovery covers the rolling seven days; named windows include today, tomorrow, and the current/upcoming Saturday–Sunday weekend. Already-started events are excluded.
- Date-only `date_to` includes that calendar day; an ISO timestamp `date_to` is an exclusive boundary. Use explicit offsets for timestamp inputs.
- A schedule contains at most three events. It is the best feasible selection within the fetched candidate set and declared ranking rules, not a guarantee of complete citywide coverage.
- The physical transfer allowance defaults to **60 minutes**. Online-to-online transitions use **5 minutes**. Hybrid attendance uses the physical allowance. Starting-location travel, distance, and live traffic are not calculated.
- The default `duration_policy="strict"` excludes events with missing or invalid ends into `needs_duration`. An explicitly chosen duration estimate makes the resulting schedule conditional; it is marked with warnings.
- Ranking combines matching topics and the upstream connection signal. Reasons identify the evidence; scores are not probabilities of making contacts.
- “Free” means listed free by the upstream service. Confirm price, registration, capacity, timing, and admission at the linked event page.

## Prerequisites

- Python 3.11+ with `venv` and `pip`. Check that the chosen Python executable has the required version.
- This repository cloned or extracted locally.
- Internet access to install dependencies and to use live mode. Sample mode needs no network after installation.
- An MCP host with local stdio-server support for conversational use.

No PulseBLR account, API key, database, browser session, Node.js installation, or `uv` installation is required for the server. The optional Gemini API client additionally requires its locked extra dependencies and a Gemini API key.

## Installation & Setup

Obtain the branch or ZIP revision that contains `tools/pulseblr-events-mcp/`. After the contribution is merged, the upstream clone command is:

```bash
git clone https://github.com/gdgcblr/open-source-agents.git
cd open-source-agents
```

Before merge, use the contribution's PR branch instead; an older checkout will not contain this tool. The folder is self-contained and can also be copied to another machine without the rest of the repository.

Run these commands from the repository root. A Python 3.11+ executable must be available as `python` on Windows or `python3` on macOS/Linux; substitute its path if needed.

### Windows PowerShell

```powershell
cd tools/pulseblr-events-mcp
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps .
```

### macOS / Linux

```bash
cd tools/pulseblr-events-mcp
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps .
```

These commands use the virtual environment directly. Shell activation and PowerShell execution-policy changes are unnecessary. Keep the lock files with the project when installing on another device. Python package installation may download build tooling; run the sample only after installation completes.

## Configuration & Environment Variables

The MCP server does not require credentials or load `.env` files. The optional Gemini client reads only a file you explicitly name with `--env-file`, or `GEMINI_API_KEY` from its own process environment. It does not pass the key to the MCP subprocess.

| Setting | Required | Default | Description |
| --- | --- | --- | --- |
| `--source live` or `--source sample` | No | `live` | Select public live data or fictional offline data |
| `--now <ISO timestamp>` | No | System clock | Sample-only fixed clock; live mode rejects it |
| `GEMINI_API_KEY` | Gemini client only | None | Put this in a Git-ignored `.env.local` and explicitly pass `--env-file .env.local`, or set it in the client process environment |
| `GEMINI_MODEL` | No | `gemini-3.5-flash-lite` | Optional model ID in the named client settings file; `--model` overrides it |

The live endpoint is fixed. The server does not accept arbitrary URLs, cookies, bearer tokens, or personal PulseBLR tool access. Never put a real API key in `.env.example`, this README, a host's committed configuration, a prompt, or a Git-tracked file.

## How to Run

The commands below start a stdio MCP process. It waits for an MCP host's protocol messages; an idle terminal is expected. Press Ctrl+C to stop a manually started process. Diagnostics go to stderr, while stdout is reserved for the MCP protocol.

### Live mode

Windows:

```powershell
.\.venv\Scripts\python.exe -m pulseblr_events_mcp --source live
```

macOS/Linux:

```bash
.venv/bin/python -m pulseblr_events_mcp --source live
```

The installed `pulseblr-events-mcp` entry point provides the same CLI. Using the environment's Python with `-m` makes the interpreter choice explicit.

### Reproducible offline demo

The packaged sample is fictional, with fixed dates and `example.com` links. It does not move its events to the current date. Use this clock to reproduce the demo:

```powershell
.\.venv\Scripts\python.exe -m pulseblr_events_mcp --source sample --now "2026-10-24T08:00:00+05:30"
```

```bash
.venv/bin/python -m pulseblr_events_mcp --source sample --now '2026-10-24T08:00:00+05:30'
```

Every sample result identifies the fictional-data mode. To switch sources, restart the server with a different `--source` argument.

### Connect any compatible model through an MCP host

All five tools are implemented by this server. The tool surface is the same whether the host uses Gemini, Claude, OpenAI, or a supported local model. A raw model API is insufficient: choose a host that supports local stdio MCP servers and tool calling for the selected model.

Configure the host with these values after replacing the generic executable path:

| Host setting | Value |
| --- | --- |
| Transport | Local `stdio` |
| Command on Windows | `C:/work/open-source-agents/tools/pulseblr-events-mcp/.venv/Scripts/python.exe` |
| Command on macOS/Linux | `/path/to/open-source-agents/tools/pulseblr-events-mcp/.venv/bin/python` |
| Live arguments | `["-m", "pulseblr_events_mcp", "--source", "live"]` |
| Reproducible sample arguments | `["-m", "pulseblr_events_mcp", "--source", "sample", "--now", "2026-10-24T08:00:00+05:30"]` |
| Environment / credentials | None required by this server |

After connecting, inspect the host's available tools: `search_events`, `get_event`, `list_topics`, `recommend_communities`, and `plan_schedule` must all appear. Then run the sample flow below. Model quality and a host's permissions affect tool use; neither changes the package's five-tool implementation.

### Manual Gemini API test: exact key location and commands

Run from `tools/pulseblr-events-mcp/` after the base installation above. Obtain a key from [Google AI Studio](https://aistudio.google.com/apikey). Use the optional locked dependencies and reinstall the package so the manual client is available:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-gemini.lock
.\.venv\Scripts\python.exe -m pip install --no-deps .
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
```

On macOS/Linux, use `.venv/bin/python` for the two pip commands and `test -f .env.local || cp .env.example .env.local` to create the local file without overwriting an existing key.

Open **`tools/pulseblr-events-mcp/.env.local`**, relative to the repository root. Add the key there after the equals sign:

```dotenv
GEMINI_API_KEY=YOUR_LOCAL_KEY
GEMINI_MODEL=gemini-3.5-flash-lite
```

`YOUR_LOCAL_KEY` is a placeholder to replace locally. `.env.local` is ignored by Git and excluded from built distributions. `.env.example` must keep its committed key value empty. The server requires no key; only this manual client reads the named file.

Start the interactive client on Windows:

```powershell
.\.venv\Scripts\python.exe -m pulseblr_events_mcp.gemini_client --env-file .env.local --source sample
```

On macOS/Linux:

```bash
.venv/bin/python -m pulseblr_events_mcp.gemini_client --env-file .env.local --source sample
```

Type the three example prompts below. The terminal shows which MCP tools Gemini calls, followed by its answer. Sample mode uses the fixed demo clock and fictional events. Type `exit` to finish. Change `--source sample` to `--source live` for real public listings; the key location stays the same.

For a single all-five-tools check:

```powershell
.\.venv\Scripts\python.exe -m pulseblr_events_mcp.gemini_client --env-file .env.local --source sample --verify-all-tools --prompt "Discover topics, find events this weekend, read an event's details, recommend relevant organisers, and plan two events with 60 minutes between physical venues."
```

The client reports success only if all five tools were actually called successfully. Its loop is bounded to six model rounds and ten tool calls per user prompt. Automatic SDK tool execution, automatic continuation, and automatic retries are disabled. This prevents a successful-looking response from hiding an unbounded agent loop.

The documented default `gemini-3.5-flash-lite` and override `--model gemini-3.8-flash` support function calling and are listed with free-tier Standard input/output pricing in [Google's pricing documentation](https://ai.google.dev/gemini-api/docs/pricing). Project eligibility, billing configuration, quotas, model access and service availability still apply. No Search or Maps grounding is used by this client. If a model returns a gateway timeout, select another available model explicitly; the client does not silently change providers or models.

The client sends your public prompts and public MCP results to Google. It keeps only bounded in-memory conversation context and writes no chat transcript. Use public event questions; do not include private work material or credentials. Key values are hidden from logs and output and are not available to the MCP server.

### Optional Google/Gemini host without this API client

For a Google-hosted model, follow the current official [Antigravity CLI quickstart](https://antigravity.google/docs/getting-started/) and [authentication guide](https://antigravity.google/docs/install/), choosing the **Antigravity CLI** tab. Its executable is `agy`. The user completes personal Google sign-in in the browser; OAuth credentials remain in the host's secure local credential storage, outside this project. This package needs no Google API key or Google model SDK.

Use the host's `/model` selector to choose a Gemini model available to the signed-in account. `/mcp` opens its MCP server manager; `/usage` shows quota. Apply the local command/arguments above. Google's [migration guide](https://antigravity.google/docs/cli/gcli-migration/) identifies `~/.gemini/config/mcp_config.json` for global MCP servers and `.agents/mcp_config.json` for workspace servers. Follow the current host documentation for its configuration schema.

As checked on 24 October 2026, Google's [plans page](https://antigravity.google/docs/plans/) describes a weekly quota for individual users without Pro/Ultra. Quotas and model access can change and depend on eligibility; this README makes no fixed request-count or model-access promise.

**Gemini CLI free-tier update:** Google's [official transition announcement](https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/) states that consumer/free individual and Google AI Pro/Ultra Gemini CLI requests stopped on 18 June 2026. Older instructions advertising free personal Google sign-in for Gemini CLI are insufficient for the current consumer route. Existing enterprise/API-backed Gemini CLI setups may still use this server through local stdio; check their applicable licensing and costs.

### Claude Desktop: local stdio configuration

Add the following entry to the host's MCP configuration, replacing the generic absolute path with the virtual environment created above. Keep the Python executable absolute so the host can launch it from any working directory.

Windows example:

```json
{
  "mcpServers": {
    "pulseblr-events": {
      "command": "C:/work/open-source-agents/tools/pulseblr-events-mcp/.venv/Scripts/python.exe",
      "args": ["-m", "pulseblr_events_mcp", "--source", "live"]
    }
  }
}
```

On macOS/Linux, use an absolute executable such as `/path/to/open-source-agents/tools/pulseblr-events-mcp/.venv/bin/python`. For an offline host demo, replace the arguments with:

```json
["-m", "pulseblr_events_mcp", "--source", "sample", "--now", "2026-10-24T08:00:00+05:30"]
```

Restart or reconnect the host after editing its configuration. These are local stdio examples; the standalone package adds tools that are not present in the existing remote PulseBLR server.

### Claude Code

The official local-server command shape is `claude mcp add --transport stdio <name> -- <command> <args...>`. For example on macOS/Linux, after replacing the generic path:

```bash
claude mcp add --transport stdio pulseblr-events -- /path/to/open-source-agents/tools/pulseblr-events-mcp/.venv/bin/python -m pulseblr_events_mcp --source live
```

For PowerShell, use the Windows virtual environment's absolute `python.exe` path as the command. See [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp) for host configuration and connection troubleshooting. The host manages its own model credentials; this server requires none.

## Example Input & Output

### Example Input

With the sample server and fixed clock configured, ask the host:

1. “Find Bengaluru developer events this weekend. Show why each matched and link the event pages.”
2. “Which communities are organising those events? Recommend three based on AI and open-source interests, using the events as evidence.”
3. “Plan at most two of those events. Leave 60 minutes between physical venues, and tell me which events cannot be scheduled because their end time is missing.”

The host should call `list_topics` before choosing supported topic/area filters and pass the returned event IDs to subsequent tools. A basic first call is:

```json
{"when": "weekend", "limit": 5}
```

### Example Output

Excerpt from a genuine `scripts/verify_mcp.py --source sample` run on 24 October 2026, using the fixed clock above. These event IDs and organisers are fictional sample data, not real listings. The verification client calls the tools directly; this is tool output rather than an invented model response.

```json
{
  "source": "sample",
  "tools_verified": [
    "get_event", "list_topics", "plan_schedule",
    "recommend_communities", "search_events"
  ],
  "returned_events": 10,
  "communities": ["Demo AI Guild", "Demo Data Circle", "Demo Open Circle"],
  "selected_ids": ["sample-ai-morning", "sample-oss-afternoon"],
  "needs_duration_ids": ["sample-missing-end"],
  "conditional_on_assumptions": false,
  "no_match_case": "passed",
  "invalid_argument_case": "passed"
}
```

The complete result also contains a fictional-data notice and a warning explaining the excluded event's missing end time.

## How to Test

For the timed review, use [the two-minute script and live scenario commands](docs/REVIEW_DEMO.md). [The saved live MCP report](docs/review_results.json) contains ten real scenarios, while [Gemini verification](docs/GEMINI_VERIFICATION.md) separately records successful model-selected calls to all five tools in live and sample modes.

Install the locked test dependencies and run the suite from this project directory.

For the full optional Gemini SDK test coverage, also install `requirements-gemini.lock`. The automated tests use fake model responses and local transports; they do not read `.env.local` or call Google's inference API. Actual model calls happen only when you explicitly run the manual client.

Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pytest
```

macOS/Linux:

```bash
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pytest
```

For manual MCP verification, connect a host in sample mode at the fixed clock, check that exactly the five documented tools are available, and execute the three-prompt flow. Check that fictional-mode notices appear, a missing end is excluded under strict policy, and results stay within the explicitly selected IDs. Then reconnect in live mode and confirm that returned links and source metadata are live.

### Verify all five tools without a model account

After installing the package, run the included real MCP client. It starts the installed server, initializes a stdio session, checks all five tools, invokes each, verifies mode labels, and tests no-match and invalid-argument responses.

Windows:

```powershell
.\.venv\Scripts\python.exe scripts/verify_mcp.py --source sample
.\.venv\Scripts\python.exe scripts/verify_mcp.py --source live
.\.venv\Scripts\python.exe scripts/check_release.py
```

macOS/Linux:

```bash
.venv/bin/python scripts/verify_mcp.py --source sample
.venv/bin/python scripts/verify_mcp.py --source live
.venv/bin/python scripts/check_release.py
```

Sample verification needs no network after installation. The optional live check contacts the public service and may fail when it is unavailable. The release guard requires a Git checkout and checks this contribution's scope, forbidden files and selected credential patterns. It prints rule names and paths, never matching values. It is not a complete secret scanner; inspect the staged diff as well.

Maintainers can build and inspect both distributions with the locked development dependencies installed:

```bash
python -m build
python scripts/check_release.py --archives
python -m ruff check .
python -m ruff format --check .
```

Use the virtual environment's Python executable in those commands, as shown in the platform-specific examples above. `dist/` is ignored and is not part of the contribution.

**Verification status (24 October 2026):**

- Windows, Python **3.12.13**, with the optional Gemini dependencies installed: **154 tests passed**, plus four subtests; Ruff lint and formatting checks passed. Real stdio sample and live sessions exercised all five tools, no-match output and invalid-argument handling.
- Ten real live MCP scenarios passed, with a dated public-data snapshot in `docs/review_results.json`. The same ten-scenario harness passed with fictional offline data, including exact physical and online transfer boundaries.
- Actual `gemini-3.5-flash-lite` API sessions called all five tools successfully in both live and sample modes. The terminal verified five successful calls in each run; no credential value was printed or passed to the MCP server. These model checks are separate from the deterministic test suite.
- A fresh Windows **Python 3.11.15** virtual environment outside the checkout installed the runtime lock with pip, then the built wheel with `--no-deps`. With `PYTHONPATH` removed, imports resolved from its `site-packages`. The copied verification client called all five tools successfully from that external directory.
- The installed wheel contained all 12 fictional sample events. Offline source checks passed with socket connection and DNS functions blocked. A portable `py3-none-any` wheel and source archive were built and checked for forbidden files and common credential patterns; no matches were found.
- macOS/Linux instructions are provided, but those operating systems were **not executed** in this validation. No claim is made that every model or host UI was exercised; the shared MCP protocol surface was verified directly.

## Known Limitations

- Live discovery depends on an independently operated public service. Outages, response changes, stale listings, and rate limits can cause errors. Use sample mode explicitly for an offline demonstration.
- Source verification timestamps and coordinates are not supplied by the current public event contract. `fetched_at` is retrieval time only. Unknown location and duration remain unknown.
- The current upstream serializer can treat absent price metadata as free. Free-only search preserves that upstream claim and cannot verify it independently.
- Communities are inferred from organiser names and observed events. They are not a verified membership directory, complete community census, or source of contact/WhatsApp/Discord links. Events without an organiser do not create invented groups.
- Discovery is bounded to 50 candidates, explicit ID resolution to 10, and a schedule to 3 events. Truncation and candidate counts matter when interpreting recommendations.
- Topic counts describe observed events in a supported named window. They are separate from the complete supported filter vocabulary and do not measure community membership.
- Transfer buffers are assumptions. The planner does not calculate routes, traffic, commute to the first event, registration feasibility, or admission guarantees.
- Sample results are fictional. Live listings can change between calls; explicit IDs preserve candidate identity without providing an immutable upstream snapshot.
- The package has no registration, calendar writes, messages, personal tracker access, authentication, database, or scraping pipeline.

## Security & Privacy Considerations

- **Secrets handling:** The MCP server needs and loads no API key, token, cookie, private environment file, or service-account credential. The optional Gemini client reads only its explicitly selected local key source, sends the key only to Google's API for authentication, and does not forward it to the MCP server or model prompt. The adapted `.gitignore` excludes local environments and common secret-file patterns. Ignoring a file does not remove a secret already tracked in Git; review staged changes before sharing.
- **Data privacy:** In live mode, the public discovery filters or event IDs needed for a request are sent to the fixed PulseBLR endpoint. Sample mode reads packaged data locally and needs no network at runtime. The optional Gemini client still needs network/model access in either data mode; its public prompts and tool results are sent to Google. Other MCP hosts separately control what they send to their model provider.
- **Public-only boundary:** The adapter uses an explicit public-operation allowlist and validated public event fields. It does not expose an arbitrary upstream executor, arbitrary URL fetching, private tools, or database access.
- **Untrusted content:** Event titles, descriptions, organiser names, and links are external data. They may contain misleading text or prompt-injection attempts. The host must treat them as evidence, never instructions. Text bounds and field allowlists reduce exposure but cannot guarantee prompt-injection resistance.
- **Execution:** The server computes filtering, grouping, and scheduling. It does not run event-supplied code or shell commands, submit forms, or write to calendars. Do not put credentials or private work details into public search queries.

## Future Improvements

- [ ] Optional caching with explicit freshness and invalidation behavior.
- [ ] Better upstream provenance, explicit unknown pricing, and duration completeness.
- [ ] Optional routing estimates with a separately documented provider and privacy boundary.
- [ ] Calendar export after schedule review, preserving all duration/transfer assumptions.

## License

This contribution is provided under the parent repository's [MIT license](LICENSE), copyright 2026 GDG Cloud Bengaluru Community. A copy is included so the standalone source distribution retains its license.

Live public event data is supplied by [PulseBLR](https://pulseblr-u9f1.vercel.app/) and its linked original sources. This contribution independently implements the local MCP package and does not copy PulseBLR's application source or aggregation pipeline. Attribution does not grant ownership or a new license over third-party event text, brands, or linked material; consult the original sources for reuse terms.
