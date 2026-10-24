# Commute Gate

> A Bengaluru commute agent that **asks when the request is unclear**, **plans only from BMTC / Namma Metro data**, and **blocks replies that do not match the tool output**.

Built for riders and for **app builders** who want reusable escalate / act / eval rules—not a one-off chatbot.

---

## Overview

### Problem Statement & Intended Users

- **Problem:** People (and in-car / in-app copilots) ask AI for the next trip while already under load — a rider heading to work, or a ride-hailing driver (Uber, Ola, Rapido) glancing at a new offer near drop-off. The model often answers a vague ask (“airport tomorrow”) as if it were complete, or it rewrites a real schedule into the wrong bus, metro line, or arrival time. That text is what the human trusts, not the hidden tool JSON.
- **Intended Users:** Daily commuters who want a grounded Bengaluru plan; app builders shipping voice-first or glanceable trip copilots; teams who need an open **gate + eval** harness so their model does not act too soon or speak past the tools.
- **Why It Matters:** A wrong route wastes a morning. A wrong line spoken to a driver competes with traffic. Open-source agents should **ask when the request is unclear**, **plan only from transit data**, and **refuse to show a reply the tools did not support** — and those rules should be editable, not locked inside a closed product.

### Key Features

- Escalates, acts, or acts with a logged assumption **before** calling routes.
- Plans from open BMTC corridors + Namma Metro (bus and metro, with alternatives).
- Scores the written reply against tool JSON (anti-hallucination), memory, and arrive-by goal.
- Policy file: add or remove gates and evals without editing the agent loop.
- Runs locally (Ollama or rules-only). No cloud API keys.

### Open-source use (app builders)

Closed models guess quietly. This repo is a **harness**, not a trainer: you run *your* model through the same gates and evals and get a labeled trace (`ESCALATE` / `PASS` / `FAIL` + evidence).

Typical loop:

1. Point `LLM_PROVIDER` / `OLLAMA_MODEL` at the model you are testing (or wrap `CommuteAgent` in your app).
2. Run a fixed set of asks (vague, full trip, “no metro”, off-topic).
3. Keep JSON traces: gate decision, tool JSON, model text, eval scores.
4. Improve the **prompt**, **tools**, or **policy** until FAIL rate drops. Those traces can also feed later preference / eval datasets — this project does not fine-tune weights itself.

Swap the commute tools for your domain; keep `policy.yaml` as the checklist.

---

## Technical Stack

- **Language & Runtime:** Python 3.10+
- **Agent loop:** Vanilla Python — extract slots → gates → `get_routes` → summary → evals
- **Models:** Ollama (`phi3:mini` default, `llama3.2:1b` optional) or `LLM_PROVIDER=none`
- **Data:** [Vonter/bmtc-gtfs](https://github.com/Vonter/bmtc-gtfs) (community BMTC GTFS) + Namma Metro station list. There is **no** Bengaluru GTFS on Hugging Face as of 2026-10; `huggingface` is an optional plug.

```
commute-gate/
├── main.py                 # CLI: --ask, --chat, --demo, --list-policy
├── policy.yaml             # enable / disable gates and evals
├── extensions/             # drop-in custom checks (see peak_hour.py)
├── commute_gate/           # agent, policy, routing, LLM providers
└── scripts/build_bengaluru_network.py
```

---

## Architecture & Data Flow

```
User request
    → extract origin / dest / time  (Ollama or rules)
    → gates                         (ESCALATE | ACT | ACT_WITH_ASSUMPTION)
    → get_routes                    (BMTC + metro; ground truth)
    → write a short plan            (Ollama or template)
    → evals                         (PASS | WARN | FAIL)
```

| Decision | Meaning |
| :--- | :--- |
| `ESCALATE` | Stop. Ask the clarifying questions. Do not invent a route. |
| `ACT` | Call tools and continue. |
| `ACT_WITH_ASSUMPTION` | Continue, but log what you assumed. |
| Eval `PASS` | Safe to show the reply. |
| Eval `FAIL` | Do not show the model text. Use tool JSON or ask a human. |

---

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com) only if you want natural-language `--ask` (`ollama serve` + `ollama pull phi3:mini`)
- No API keys

---

## Installation & Setup

```bash
cd agents/commute-gate
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Optional: refresh BMTC corridors from the public CSV (a snapshot is already in the repo):

```bash
python3 scripts/build_bengaluru_network.py
```

Optional: local model

```bash
ollama serve
ollama pull phi3:mini              # ~2.2 GB
# or: ollama pull llama3.2:1b      # ~1.3 GB, then set OLLAMA_MODEL=llama3.2:1b
```

---

## Configuration & Environment Variables

Copy `.env.example` to `.env`. Nothing is required for `--demo` with `--llm none`.

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `LLM_PROVIDER` | No | `ollama` | `ollama` or `none` (rules only) |
| `OLLAMA_HOST` | No | `http://127.0.0.1:11434` | Local Ollama |
| `OLLAMA_MODEL` | No | `phi3:mini` | Small local model |
| `ROUTE_PROVIDER` | No | `bengaluru` | `bengaluru`, `fixture`, or `huggingface` |
| `HF_DATASET` | No | empty | Only if you use a custom Hugging Face table |
| `POLICY_FILE` | No | `policy.yaml` | Gate / eval list |
| `POLICY_GATES` | No | — | Comma list; overrides file (e.g. `required_slots,known_places`) |
| `POLICY_EVALS` | No | — | Comma list; overrides file |
| `POLICY_EXTENSIONS` | No | `extensions` | Folders of extra `*.py` plugins |
| `LOG_LEVEL` | No | `info` | Reserved |

---

## How to Run

From `agents/commute-gate`:

```bash
# 1) Vague → ask questions (no fake route)
python3 main.py --ask "How do I get to the airport tomorrow morning?"

# 2) Full trip → BMTC / metro plan
python3 main.py --ask "How do I get from Koramangala to Indiranagar by 9am?"
python3 main.py --ask "How do I get from electronic city to majestic by 9am?"

# 3) Interactive
python3 main.py --chat
```

No Ollama (deterministic demos):

```bash
python3 main.py --demo escalate --llm none
python3 main.py --demo pass --llm none
python3 main.py --demo hallucinate --llm none   # tool OK, summary lies → FAIL
python3 main.py --demo memory --llm none
python3 main.py --list-policy
```

One-off overrides: `--llm ollama|none`, `--model llama3.2:1b`, `--routes bengaluru|fixture`.

---

## Example Input & Output

**Ambiguous**

```
How do I get to the airport tomorrow morning?
```

```json
{
  "decision": "ESCALATE",
  "fired": ["required_slots"],
  "clarifying_questions": [
    "Where are you leaving from (starting address or neighborhood)?",
    "Do you need to arrive by a specific time, or leave after a specific time?"
  ]
}
```

**Grounded**

```
How do I get from electronic city to majestic by 9am?
```

```
ACT → Yellow 08:20 (22 min) → Green 08:46 (14 min) → arrive 08:56
Alternative: bus 171-G, 36 min
Eval: PASS if the written summary only uses those lines and minutes
```

If the model writes `G171-G` or drops Green, **tool_faithfulness = FAIL**. The route is still valid; the sentence is not safe to show.

---

## How to Test

```bash
cd agents/commute-gate
python3 main.py --demo escalate --llm none      # exit 0, ESCALATE
python3 main.py --demo pass --llm none          # exit 0, eval PASS
python3 main.py --demo hallucinate --llm none   # exit 1, tool_faithfulness FAIL
python3 main.py --list-policy
```

Add a neighborhood in `commute_gate/fixtures/places.json`, then run `python3 scripts/build_bengaluru_network.py`.

---

## Customize gates and evals

The loop does not change. **You change the list.**

```
ask → [your gates] → tools → write reply → [your evals] → show / hide / escalate
```

**Turn checks on/off** in `policy.yaml` (comment a line to disable):

```yaml
gates:
  - required_slots     # drop if your UI already collected origin / dest / time
  - known_places
  - vague_place
  - accessibility
  # - peak_hour        # example plugin in extensions/peak_hour.py
evals:
  - tool_available
  - tool_faithfulness
  - memory_consistency
  - goal_alignment
```

**Use it in an app:**

```python
from commute_gate.agent import CommuteAgent
from commute_gate.policy import PolicySpec

agent = CommuteAgent(
    policy=PolicySpec(
        gates=["required_slots", "known_places"],
        evals=["tool_available", "tool_faithfulness"],
        extension_dirs=["extensions"],
    )
)
run = agent.run("Koramangala to Indiranagar by 9am")

if run.gate.decision.value == "ESCALATE":
    ask_user(run.gate.clarifying_questions)
elif run.report and run.report.overall.value == "FAIL":
    show_tool_json_only(run.step.tool_result)   # do not show LLM text
else:
    show(run.step.agent_summary)
```

**Add a rule:** create `extensions/my_check.py` with `name`, `kind` (`gate` or `eval`), and `run()`, then add that `name` under `gates` or `evals`. See `extensions/peak_hour.py`.

---

## Known Limitations

- BMTC times come from an unofficial community GTFS and can be off.
- Same-day `HH:MM` only. No live vehicle positions.
- Place list is a curated Bengaluru set, not every stop in the city.
- Small local models can mangle line names; that is why eval exists.
- Hugging Face provider does nothing until you set `HF_DATASET`.

---

## Security & Privacy Considerations

- **Secrets:** No cloud keys. Do not commit `.env`.
- **Data:** Default path stays on this machine (Ollama + local JSON).
- **Safety:** Planning only. No bookings or payments.

---

## Future Improvements

- [ ] Live GTFS-RT / OpenTripPlanner adapter
- [ ] Hugging Face Bengaluru feed if one is published
- [ ] Replan when eval returns WARN / FAIL
- [ ] Automated tests for policy checks

---

## License

Contributed under this repository’s MIT license.  
BMTC extract: [Vonter/bmtc-gtfs](https://github.com/Vonter/bmtc-gtfs) (unofficial timetables).
