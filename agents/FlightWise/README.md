# Flightwise AI

Flightwise AI gathers a traveler's requirements, searches a provider-neutral
flight interface, and ranks the five best matches. This MVP uses synthetic demo
data; it does not retrieve real flights or provide bookable fares.

## What it collects

- Origin, destination, and departure date
- Optional return date (one-way or round trip)
- Passenger count and total budget
- Checked-bag and carry-on requirements
- Ranking preference: balanced, cheapest, fastest, or fewest stops

## Run locally

Python 3.10+ and a Google AI Studio API key are required.

```bash
cd open-source-agents/agents
source .venv/bin/activate
# Create a local env file only if one does not already exist:
[ -f FlightWise/.env ] || cp FlightWise/.env.example FlightWise/.env
# Add your GOOGLE_API_KEY to FlightWise/.env
adk web
```

Open the local URL printed by ADK and select `FlightWise`. For a terminal chat:

```bash
adk run FlightWise
```

If you do not already have an environment with ADK installed, create one and
install this agent's dependency:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r FlightWise/requirements.txt
```

Do not overwrite an existing `FlightWise/.env`; it may contain your local API
key. Never copy secrets into the example file.

## Example request

> Find a round-trip flight from BLR to DEL, leaving 2026-12-01 and returning
> 2026-12-08. There are two passengers, our total budget is INR 30,000, we need
> one checked bag and a carry-on, and we prefer the cheapest option.

The agent asks follow-up questions when required details are missing, then
returns up to five ranked options with a score breakdown and baggage/budget
status. All results are marked as synthetic and not bookable.

## Design

```text
Conversation -> ADK agent -> search_flights() -> normalized mock records
                                               -> flight_ranking.py -> top five
```

`search_flights()` is the provider adapter boundary. A future live provider
should map its response to the same flight fields and keep the ranking module
independent of provider-specific APIs. Provider credentials and API errors
should remain inside that adapter.

## Validate

From `open-source-agents/agents`:

```bash
python -m unittest discover -s FlightWise -p 'test_*.py'
```

## Agent evaluations

The ADK eval set covers missing-detail follow-up, one-way search, round-trip
search, tool-use correctness, and clear disclosure that search results are
synthetic. The offline unit tests validate the eval files and tool trajectory
without making model calls.


With `GOOGLE_API_KEY` configured, run the model-backed ADK evaluations from
`open-source-agents/agents`:

```bash
adk eval FlightWise FlightWise/evals/flightwise.evalset.json \
  --config_file_path FlightWise/evals/eval_config.json \
  --print_detailed_results
```

This invokes Gemini for agent responses and response-quality judging, so it
requires API access and may incur model usage charges.

## Limitations

- Search results are generated sample data, not live schedules, fares, or
  availability.
- The mock supports INR only and does not verify airports or dates with an
  airline/provider.
- Baggage allowances may be unknown; always verify with the airline before
  booking.
- This MVP compares options; it does not book or reserve flights.
