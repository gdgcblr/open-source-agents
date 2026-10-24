# Gemini API and MCP verification

Recorded 24 October 2026. These are actual runs, not example model answers invented for documentation. The configured key stayed in a local Git-ignored `.env.local` file; no credential value or hash is recorded here.

## Model and client

- Official `google-genai==2.33.0` Python SDK.
- Explicit model: `gemini-3.5-flash-lite`.
- Fixed Google API origin with explicit HTTPX transport, environment proxies disabled, automatic retries disabled, and SDK automatic tool execution/continuation disabled.
- Five tools discovered from the real local stdio MCP server. The client executed only declared function names and returned actual tool results to Gemini.

## Actual sample run

Command, from the project directory:

```powershell
.\.venv\Scripts\python.exe -m pulseblr_events_mcp.gemini_client --env-file .env.local --source sample --model gemini-3.5-flash-lite --verify-all-tools --prompt "Demonstrate all five PulseBLR MCP capabilities using only fictional sample data. Discover topics, search this weekend, get an event's details, recommend three organisers, and plan two events with a 60 minute transfer buffer. Clearly label fictional data and missing end times."
```

Actual client trace:

```text
search_events: ok (events=10)
get_event: ok
list_topics: ok
recommend_communities: ok (communities=2)
plan_schedule: ok
Verified all five MCP tools (5 calls).
```

Gemini labelled the data fictional, cited the example.com event link, described the unknown-finish listing, and chose `sample-ai-morning` plus `sample-cloud-evening` from the IDs it supplied to the planner. It did not submit registration or modify data. This run exercises model tool calling; the separate offline scenario harness checks exact 60-minute and 5-minute scheduling boundaries deterministically.

## Actual live run

```powershell
.\.venv\Scripts\python.exe -m pulseblr_events_mcp.gemini_client --env-file .env.local --source live --model gemini-3.5-flash-lite --verify-all-tools --prompt "Use only live public PulseBLR tool data. Discover valid topics, find upcoming free in-person AI/ML events in Koramangala this weekend, read details of one returned event, recommend the organisers represented by those event IDs, and plan at most two of those events with a 60 minute transfer buffer and strict end-time policy. Explain missing data and do not invent a second event if no valid pair exists. Include the real event links."
```

Actual client trace:

```text
search_events: ok (events=3)
get_event: ok
list_topics: ok
recommend_communities: ok (communities=1)
plan_schedule: ok
Verified all five MCP tools (5 calls).
```

The model returned public links for [AI Safety Mixer: Embodied AI | SAFL](https://pulseblr-u9f1.vercel.app/events/6ad9c1b912a908293f6517b7) and [SAFL AI Futures Dialogue #2](https://pulseblr-u9f1.vercel.app/events/6ad9c1ba12a908293f6517b8). The organiser was Secure AI Futures Lab | SAFL. The model used a two-ID candidate set for its schedule: the Mixer ran 18:00–20:30 IST and the Dialogue 19:00–20:00 IST. It selected the Mixer and explained the overlap instead of inventing a valid second event.

The source search contained three listings, while the model used two IDs in this plan. This is evidence of a successful, bounded tool workflow over those IDs, not proof of a globally best itinerary or exhaustive model interpretation. Listings, counts, availability and model wording can change between runs. Free means listed free by the source, with the upstream defaulting caveat documented in the README.

## Availability and limits

The lighter model generated successfully. Earlier `gemini-3.8-flash` generation attempts returned Google gateway timeouts; model metadata access alone did not establish successful generation. Model selection was changed explicitly. There is no silent model/provider fallback.

Google lists free-tier pricing for the selected model, but quota, billing configuration, eligibility and availability depend on the Google project. This record is not an assertion that every API key has quota or that every Gemini model is available. Only public prompts and public event results were sent in these checks.

Nothing was pushed to GitHub as part of this verification.
