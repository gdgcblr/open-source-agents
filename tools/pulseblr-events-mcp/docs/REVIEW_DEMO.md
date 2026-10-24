# PulseBLR Event Planner: two-minute review

Run commands from `tools/pulseblr-events-mcp`, the directory containing `pyproject.toml`. No push is required.

## Spoken script (120 seconds)

**0–20 seconds — problem**

“Finding a Bengaluru tech event takes several searches. Then I still need to compare location, timing, price and organizers. This contribution gives an assistant five practical tools to turn public listings into an explainable shortlist and schedule.”

**20–40 seconds — architecture and five functions**

“The local Python server speaks standard MCP over stdio. It reads the anonymous public PulseBLR service. `list_topics` discovers supported filters, `search_events` finds candidates, `get_event` retrieves details, `recommend_communities` groups observed organizers, and `plan_schedule` checks timing. Filtering and planning execute in Python behind the tools.”

**40–90 seconds — live demonstration**

Show the live Gemini trace or the dated live scenario report. Use the preparation commands below before the timed pitch so network latency does not consume the presentation.

“Here I ask Gemini for listed-free, in-person AI events in Koramangala this weekend. The actual run found three and successfully called all five tools. It retrieved the AI Safety Mixer, identified Secure AI Futures Lab as the observed organizer, and kept the public event links. For planning it used two event IDs: one runs from six to eight-thirty, the other from seven to eight. They overlap, so the planner returns one event. It does not manufacture a second event just because I asked for up to two.”

**90–110 seconds — guardrails and evidence**

“All ten live MCP scenarios passed, including missing durations, no matches, invalid inputs and rejecting an unknown personal tool. The server is read-only and key-free; the optional client keeps its Gemini key out of MCP. A separate fresh installation passed. Labelled offline fixtures verify exact sixty-minute physical and five-minute online gaps.”

**110–120 seconds — close**

“The result is a reusable, read-only MCP contribution with source evidence, explicit uncertainty and a reproducible offline fallback. Event price, registration and traffic still need human verification.”

## Review commands

```powershell
# Ten real MCP scenarios against anonymous public listings; writes the dated report.
.\.venv\Scripts\python.exe scripts\review_scenarios.py --source live

# Read the saved evidence: source, timestamps, public names/links, arguments and assertions.
Get-Content -LiteralPath docs\review_results.json

# Independent, bundled protocol verification: initializes MCP and invokes all five tools.
.\.venv\Scripts\python.exe scripts\verify_mcp.py --source live
```

The harness uses the official `mcp.ClientSession` and launches a real stdio server subprocess. It calls tools over the protocol, not their Python functions. It reads no env file, invokes no model, uses at most five IDs per recommendation/planning call, and makes at most sixteen public read operations plus protocol handshakes per live run. Do not loop rapidly against the public service's 120/minute limit.

For a manual MCP host connection, configure the command as the absolute path to `.venv\Scripts\python.exe`, arguments `-m pulseblr_events_mcp --source live`, and working directory as this package directory. List the tools, then use the arguments shown in `review_results.json`, substituting newly returned IDs. Use `format: "offline"` for in-person attendance. A directly launched stdio server waits quietly for MCP input; an idle terminal is normal. Use Ctrl+C to stop it.

## Recorded public snapshot

At **24 October 2026, 14:16 IST** (08:46 UTC), all **10/10** live scenarios passed. This is a dated snapshot, not a guarantee of current event availability. Rerun the command before presenting; counts and examples may change.

| Evidence | Recorded result |
| --- | --- |
| Narrow search | Three AI/ML, listed-free, offline Koramangala events within the returned weekend bounds |
| Real example | [AI Safety Mixer: Embodied AI \| SAFL](https://pulseblr-u9f1.vercel.app/events/6ad9c1b912a908293f6517b7), 24 Oct, 18:00–20:30 IST |
| Another example | [SAFL AI Futures Dialogue #2 \| Dr. Roshni Lulla](https://pulseblr-u9f1.vercel.app/events/6ad9c1ba12a908293f6517b8), 24 Oct, 19:00–20:00 IST |
| Broad search | Ten returned of 66 matching; `candidate_pool_truncated=true` |
| Strict plan over five explicit IDs | [CyberSwaraj: They Warned Us](https://pulseblr-u9f1.vercel.app/events/6ac7618cd9ed474e5609246a), 17:00–21:00 IST; only one selected |
| Missing-end exclusions | UX for AI SDLC Masterclass; Monthly Meetup - October 2026: Stop Designing Screens. Start Designing Systems. |
| Communities | Observed organizers and event evidence; no invented membership or contact links |
| Error cases | Unique no-match query returned `[]`; `max_events=99` returned `is_error`; local unknown `my_people` returned `is_error` |

“Free” means listed free upstream; missing price metadata can default to free. `fetched_at` is retrieval time, not independent source verification. The first-five candidate plan is bounded; it is not a globally optimal Bengaluru itinerary. Community scores are ranking signals. Transfer allowances are assumptions, not live traffic estimates or admission guarantees.

## Explicit offline fallback

```powershell
# No network after dependencies are installed. Does not overwrite the live report.
.\.venv\Scripts\python.exe scripts\review_scenarios.py --source sample --output "$env:TEMP\pulseblr-review-sample.json"
.\.venv\Scripts\python.exe scripts\verify_mcp.py --source sample
```

Announce: **“I am switching to fictional sample events at the fixed clock 24 October 2026, 08:00 IST.”** Every sample response carries fictional-data warnings and example.com links. The sample harness verifies the 09:00–11:00 morning event and 12:00–14:00 afternoon event leave exactly 60 minutes, excludes the unknown-finish event, and separately checks an online pair with exactly five minutes between sessions. These examples are not live listings.

## Optional Gemini presentation

The MCP harness above needs no Gemini key. Real Google API checks on **24 October 2026**, using `gemini-3.5-flash-lite`, separately passed **all five model-selected MCP tool calls in both sample and live modes**. Both client runs printed `Verified all five MCP tools (5 calls)`. The local credential was not included in the trace or model context. See [the recorded Gemini verification](GEMINI_VERIFICATION.md).

In the live model run, the search returned three listings. Gemini passed a two-event candidate set to the planner; it selected the 18:00–20:30 AI Safety Mixer and rejected the overlapping 19:00–20:00 Dialogue. That is a bounded plan over those selected IDs, not a claim about the best pair among every event in the search or city.

For the optional model demonstration, with the existing local settings file configured:

```powershell
# Sends the public prompt and fictional tool results to Google; uses the named local settings file.
.\.venv\Scripts\python.exe scripts\chat_gemini.py --env-file .env.local --source sample --verify-all-tools
```

Use the direct MCP harness if the model provider is unavailable. A model-provider failure does not invalidate the separately recorded MCP run, and an MCP pass alone does not prove model tool calling.
