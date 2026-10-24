# shift-planner-agent

> A Google ADK agent that analyses a gig driver's past shifts and tells them, in simple Hinglish, when and where they earned the most.

## Overview

### Problem Statement & Intended Users

Ola/Uber drivers and delivery partners work irregular shifts across different areas and times, but rarely see a clear picture of which slots actually paid best after fuel costs. This agent reads a driver's own shift history (a CSV file) and answers questions such as "Kal kab aur kahan nikalun?" (When and where should I go tomorrow?).

Intended users: gig drivers and delivery partners, and developers who want a small example of an ADK agent that keeps all calculations in plain Python tools and uses the LLM only for tool selection and explanation.

### Key Features

- **Calculations done by code, not the LLM.** All numbers come from three read-only Python tools.
- **Net earnings per hour** (earnings minus fuel cost), grouped by area, time block or weekday.
- **Best slots** (area + time block), with an optional weekday/weekend filter.
- **Hinglish answers** that tell the user when the data is too thin to trust.
- **Runs on bundled synthetic data**, so no real driver data is needed to try it.

## Technical Stack

- Python 3.12
- [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) 2.13.0
- Gemini via Vertex AI (default model `gemini-3.8-flash`) or a Gemini API key
- Python standard library only for the analysis tools (`csv`, `datetime`, `collections`)

## Architecture & Data Flow

```
User question
     |
     v
ADK root_agent (shift_planner_agent, Hinglish instructions)
     |  chooses tools
     v
load_trips / earnings_summary / best_slots   (tools.py, plain Python)
     |  reads
     v
sample_trips.csv  (or your own CSV inside this folder)
     |  numbers returned to the agent
     v
Gemini explains the numbers in Hinglish  -->  Answer
```

Project layout:

```
shift-planner-agent/
├── shift_planner/
│   ├── __init__.py
│   ├── agent.py        # ADK root_agent and instructions
│   └── tools.py        # read-only analysis tools
├── sample_trips.csv    # SYNTHETIC data: 28 shifts, 4 Bengaluru areas
├── requirements.txt
├── .env.example
└── README.md
```

| Tool | What it does |
|---|---|
| `load_trips` | Validates the CSV; reports shift count, areas and date range |
| `earnings_summary` | Net earnings per hour grouped by `area`, `block` (morning/afternoon/evening/night) or `day` |
| `best_slots` | Top area + time-block combinations; slots with fewer than 2 shifts are ignored |

## Prerequisites

- Python 3.12 (other 3.x versions are untested)
- One of:
  - A Google Cloud project with the Vertex AI API enabled (this is the setup the author tested), or
  - A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) (untested by the author)

## Installation & Setup

```bash
git clone https://github.com/gdgcblr/open-source-agents.git
cd open-source-agents/agents/shift-planner-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example shift_planner/.env
```

Then edit `shift_planner/.env` (see the next section). ADK loads the `.env` file from the agent folder (`shift_planner/`). If you use Vertex AI, enable the API once:

```bash
gcloud services enable aiplatform.googleapis.com
```

## Configuration & Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `GOOGLE_GENAI_USE_VERTEXAI` | yes | `TRUE` for Vertex AI, `FALSE` for an API key |
| `GOOGLE_CLOUD_PROJECT` | Vertex only | Your Google Cloud project ID |
| `GOOGLE_CLOUD_LOCATION` | Vertex only | Region, for example `global` |
| `GOOGLE_API_KEY` | API key only | Gemini API key |
| `SHIFT_AGENT_MODEL` | no | Overrides the default model `gemini-3.8-flash` |

Vertex AI example for `shift_planner/.env`:

```
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=global
```

Model names and availability change and differ by project and region. When the author first used `gemini-2.5-flash` in `us-central1`, Vertex returned `404 NOT_FOUND`. If you see that error, set `SHIFT_AGENT_MODEL` to a model available in your project.

## How to Run

Run from this folder (`agents/shift-planner-agent`) with the virtual environment active:

```bash
adk run shift_planner      # chat in the terminal
adk web                    # browser dev UI
```

To use your own data, place a CSV in this folder with the columns below and ask the agent to use that file name. The tools only read files inside this project folder.

```
date,start_time,end_time,area,earnings,km,fuel_cost
2026-09-28,18:00,21:00,Koramangala,837,36.7,88
```

Money is in INR and times are 24-hour `HH:MM`.

## Example Input & Output

Real run on `sample_trips.csv` using Vertex AI, ADK 2.13.0 and Python 3.12 on Google Cloud Shell, October 2026.

### Example Input

```
Kal kab aur kahan nikalun?
```

### Example Output

```
Aapke purane data (28 shifts) ke hisaab se, yeh sabse acche time aur area hain:

1. **Koramangala (Evening)**: lagbhag **₹240.5/ghanta** net kamai (4 shifts)
2. **Indiranagar (Evening)**: lagbhag **₹170.7/ghanta** net kamai (3 shifts — *dhyan rahe yahan shifts kam hain, toh andaza pakka nahi hai*)
3. **HSR Layout (Evening)**: lagbhag **₹153.5/ghanta** net kamai (7 shifts)

Overall, **Evening (shaam)** ka time sabse best raha hai (average **₹181.5/ghanta** net).

*(Note: Net kamai ka matlab hai kul kamai mein se petrol ka kharcha nikal kar per ghanta bachat. Yeh sirf purane data se andaza hai, future ki koi guarantee nahi hai.)*
```

The wording is generated by the LLM and will vary between runs. The numbers come from the tools.

## How to Test

There is no automated test suite. Manual verification, which needs **no API key and no LLM**, is to call the tools directly:

```bash
python3 -c "import importlib.util as u;s=u.spec_from_file_location('t','shift_planner/tools.py');t=u.module_from_spec(s);s.loader.exec_module(t);print(t.best_slots(3,'any')['slots'])"
```

Expected output on the bundled sample data:

```
[{'name': 'Koramangala / evening', 'net_per_hour': 240.5, 'shifts': 4, 'hours': 12.0}, {'name': 'Indiranagar / evening', 'net_per_hour': 170.7, 'shifts': 3, 'hours': 11.0}, {'name': 'HSR Layout / evening', 'net_per_hour': 153.5, 'shifts': 7, 'hours': 21.0}]
```

To check the full agent, run `adk run shift_planner`, ask the question above, and confirm the figures match this output. The agent's numbers should always match the tool output.

## Known Limitations

- **Needs a model API.** Each answer makes several model calls (typically `load_trips`, an analysis tool, then the final answer). Cost, quota and latency depend on your account and model; responses were noticeably slow in the author's testing.
- **Synthetic sample data.** `sample_trips.csv` was generated for this demo and does not describe real drivers, earnings or demand.
- **Past data only.** The agent reports historical averages. It does not account for traffic, surge pricing, weather, festivals or competition, and it does not predict future earnings.
- **Small samples are noisy.** Some slots in the sample have only 2 to 4 shifts. The agent is told to mention this, but as an LLM it may not always do so.
- **LLM output varies.** Wording, and sometimes which tools are called, can differ between runs.
- **Simplified time blocks.** Shifts are bucketed by start time only (morning 06-11, afternoon 11-16, evening 16-21, otherwise night).
- **Net earnings only subtract fuel.** Vehicle wear, insurance, platform fees and taxes are ignored.
- **Limited testing.** Tested only on Google Cloud Shell (Linux) with Vertex AI. Windows, macOS and the API-key setup are untested.
- **Not financial advice.** This is a demonstration project.

## Security & Privacy Considerations

- No credentials are committed. `.env` files are git-ignored and `.env.example` contains placeholders only.
- The tools are **read-only** and can only read files inside this project folder; paths that escape it are rejected.
- The agent cannot run shell commands or modify files.
- **Your shift data is sent to the model provider.** Tool results (areas, times, earnings) are passed to Gemini to write the answer. Do not use data you are not allowed to share, and review your provider's data terms before using real driver data.
- The bundled data is synthetic and contains no personal information.

## Future Improvements

- Expose the tools through an MCP server so other agents and clients can reuse them.
- Add automated tests for the tool functions.
- Add optional inputs such as day-specific filters, weather and event data.
- Support multiple currencies and more time-block settings.
- Add a confidence indicator based on the number of shifts behind each recommendation.

## License

MIT, same as the parent repository.
