# gemini-token-cost-tracker

A conversational **Google ADK + Gemini** agent that tracks Gemini token usage and cost, explains where the money goes, and recommends concrete, quantified savings. It also **tracks its own token spend** through an ADK `after_model_callback`.

> Fill in the sections from the repo's `template/README.md` if its headings differ from the ones below.

## What it does
| Ask the agent | Tool used |
|---|---|
| "How much would this prompt cost on 2.5 Pro?" | `count_tokens`, `estimate_cost` |
| "Run this prompt and tell me what it cost" | `track_prompt` |
| "What did I spend this week?" | `get_usage_report` |
| "How can I cut my bill?" | `suggest_optimizations` |
| "Compare models for 2k in / 500 out" | `compare_models` |
| "Alert me above $5 a day" | `set_budget`, `check_budget` |

`suggest_optimizations` is deterministic Python (model downgrades, thinking-token share, context caching for repeated prompts, output limits). The LLM only explains the numbers, so it cannot make them up.

## Prerequisites
- Python 3.10+
- A Gemini API key: https://aistudio.google.com/apikey

## Setup
```bash
cd agents/gemini-token-cost-tracker
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then paste your GOOGLE_API_KEY
```

## Run
```bash
python seed_demo.py         # optional: fake history, no API spend
adk web                     # open http://localhost:8000, pick "cost_tracker"
# or terminal chat:
adk run cost_tracker
```

## Example
```
You:   How can I cut my Gemini bill this week?
Agent: You spent $1.10 over 48 calls. Potential savings: about $0.65.
       1. gemini-2.5-pro -> gemini-2.5-flash for simple tasks: save ~$0.36.
       2. 62% of gemini-3.1-pro output is hidden thinking. Lower the
          thinking budget for routine prompts: save ~$0.17.
       3. Cache the 12k-token prompt you sent 8 times: save ~$0.09.
```
(Output from `seed_demo.py` data; your numbers will differ.)

## Test
```bash
pytest -q
```
The tests cover cost math, long-context tiers, caching discounts and the optimization rules. They need no API key.

## Pricing accuracy
Prices live in `pricing.json` (USD per 1M tokens). Google changes them often. **Verify against https://ai.google.dev/gemini-api/docs/pricing and edit the file.** Unknown models are reported, not guessed.

## Structure
```
cost_tracker/
  agent.py     # ADK root_agent + self-tracking callback
  tools.py     # function tools
  pricing.py   # cost math
  store.py     # SQLite log
pricing.json  seed_demo.py  tests/
```
